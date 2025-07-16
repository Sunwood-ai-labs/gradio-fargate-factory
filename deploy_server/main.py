from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import subprocess
import boto3
from loguru import logger
import os
from dotenv import load_dotenv

load_dotenv()

logger.add("deploy_server.log", rotation="1 MB")
app = FastAPI()

AWS_REGION = "ap-northeast-1"
CLUSTER_NAME = "gradio-ecs-cluster"

class DeployRequest(BaseModel):
    app_name: str
    docker_context: str = "./"  # Dockerfileのあるディレクトリ
    dockerfile: str = "Dockerfile"  # Dockerfile名（省略可）
    alb_path: str  # 例: "/image-filter/*"
    git_repo_url: str | None = None  # 追加: クローンするGitリポジトリURL（省略可）

@app.post("/deploy")
def deploy_app(req: DeployRequest):
    import tempfile
    import shutil

    app_name = req.app_name
    docker_context = req.docker_context
    dockerfile = req.dockerfile

    temp_dir = None
    # git_repo_urlが指定されていればクローン
    if req.git_repo_url:
        # 環境変数でクローン先ベースディレクトリを指定可能（デフォルト: 絶対パス）
        import datetime
        tmp_base = os.getenv("CLONE_BASE_DIR", "/home/cc-company/gradio-fargate-factory/tmp")
        tmp_base = os.path.abspath(tmp_base)
        os.makedirs(tmp_base, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        temp_dir = os.path.join(tmp_base, f"{app_name}_{timestamp}")
        try:
            subprocess.check_call([
                "git", "clone", req.git_repo_url, temp_dir
            ])
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Git clone failed: {e}")
        docker_context = temp_dir

    try:
        # AWS情報取得
        sts = boto3.client("sts", region_name=AWS_REGION)
        account_id = sts.get_caller_identity()["Account"]
        ecr = boto3.client("ecr", region_name=AWS_REGION)
        ecs = boto3.client("ecs", region_name=AWS_REGION)

        # ECRリポジトリURL取得（なければ作成）
        try:
            ecr_url = ecr.describe_repositories(repositoryNames=[app_name])["repositories"][0]["repositoryUri"]
        except ecr.exceptions.RepositoryNotFoundException:
            repo = ecr.create_repository(repositoryName=app_name)
            ecr_url = repo["repository"]["repositoryUri"]

        # Dockerログイン
        login_pw = subprocess.check_output([
            "aws", "ecr", "get-login-password", "--region", AWS_REGION
        ]).decode().strip()
        login_cmd = [
            "docker", "login",
            "--username", "AWS",
            "--password-stdin",
            f"{account_id}.dkr.ecr.{AWS_REGION}.amazonaws.com"
        ]
        proc = subprocess.Popen(login_cmd, stdin=subprocess.PIPE)
        proc.communicate(input=login_pw.encode())
        if proc.returncode != 0:
            raise Exception("Docker login failed")

        # Dockerビルド＆プッシュ
        import traceback
        try:
            result = subprocess.run(
                [
                    "docker", "build", "-t", f"{app_name}:latest", "-f", dockerfile, "."
                ],
                capture_output=True,
                text=True,
                cwd=docker_context
            )
            if result.returncode != 0:
                err_msg = (
                    f"docker build failed (exit code {result.returncode})\n"
                    f"stdout:\n{result.stdout}\n"
                    f"stderr:\n{result.stderr}\n"
                    f"{traceback.format_exc()}"
                )
                raise HTTPException(status_code=500, detail=err_msg)
        except Exception as e:
            err_msg = f"docker build exception: {e}\n{traceback.format_exc()}"
            raise HTTPException(status_code=500, detail=err_msg)
        subprocess.check_call([
            "docker", "tag", f"{app_name}:latest", f"{ecr_url}:latest"
        ])
        subprocess.check_call([
            "docker", "push", f"{ecr_url}:latest"
        ])


        # ALBリスナールール追加
        alb_listener_arn = os.environ.get("ALB_LISTENER_ARN")
        if not alb_listener_arn:
            raise Exception("ALB_LISTENER_ARN環境変数が未設定です")
        alb_path = req.alb_path

        elbv2 = boto3.client("elbv2", region_name=AWS_REGION)

        # ターゲットグループ作成（既存があれば使う）
        tg_name = f"{app_name}-tg"
        vpc_id = os.environ.get("VPC_ID")
        if not vpc_id:
            raise Exception("VPC_ID環境変数が未設定です")
        try:
            tg_arn = elbv2.describe_target_groups(Names=[tg_name])["TargetGroups"][0]["TargetGroupArn"]
        except Exception:
            tg = elbv2.create_target_group(
                Name=tg_name,
                Protocol="HTTP",
                Port=7860,
                VpcId=vpc_id,
                TargetType="ip",
                HealthCheckPath="/",
                HealthCheckProtocol="HTTP"
            )
            tg_arn = tg["TargetGroups"][0]["TargetGroupArn"]

        # ALBリスナールール追加（既存パス重複はスキップ）
        rules = elbv2.describe_rules(ListenerArn=alb_listener_arn)["Rules"]
        for rule in rules:
            for cond in rule.get("Conditions", []):
                if cond.get("Field") == "path-pattern" and alb_path in cond.get("Values", []):
                    break
            else:
                continue
            break
        else:
            elbv2.create_rule(
                ListenerArn=alb_listener_arn,
                Priority=1000,  # TODO: 動的に調整
                Conditions=[{"Field": "path-pattern", "Values": [alb_path]}],
                Actions=[{"Type": "forward", "TargetGroupArn": tg_arn}]
            )

        # ECSサービス存在確認→なければ作成、あれば更新
        task_definition = os.environ.get("TASK_DEFINITION", app_name)
        # サブネットIDは SUBNETS > PUBLIC_SUBNET_IDS > PRIVATE_SUBNET_IDS の順で自動参照
        subnets_env = os.environ.get("SUBNETS")
        if not subnets_env:
            subnets_env = os.environ.get("PUBLIC_SUBNET_IDS") or os.environ.get("PRIVATE_SUBNET_IDS") or ""
        subnets = [s for s in subnets_env.split(",") if s]
        security_groups = [s for s in os.environ.get("SECURITY_GROUPS", "").split(",") if s]

        # CloudWatch Logsのロググループを毎回存在確認＆なければ作成
        logs = boto3.client("logs", region_name=AWS_REGION)
        log_group_name = f"/ecs/{app_name}"
        try:
            resp = logs.create_log_group(logGroupName=log_group_name)
            logger.info(f"create_log_group response: {resp}")
            logger.info(f"Created log group: {log_group_name}")
        except logs.exceptions.ResourceAlreadyExistsException:
            logger.info(f"Log group already exists: {log_group_name}")
        except Exception as e:
            logger.exception(f"Exception during create_log_group: {e}")
        # ロググループ存在確認
        try:
            groups = logs.describe_log_groups(logGroupNamePrefix=log_group_name).get("logGroups", [])
            logger.info(f"describe_log_groups result: {groups}")
            if not any(g["logGroupName"] == log_group_name for g in groups):
                logger.error(f"Log group {log_group_name} does NOT exist after create attempt!")
                raise HTTPException(status_code=500, detail=f"Log group {log_group_name} does NOT exist after create attempt!")
        except Exception as e:
            logger.exception(f"Exception during describe_log_groups: {e}")
            raise HTTPException(status_code=500, detail=f"Exception during describe_log_groups: {e}")

        # タスク定義存在確認＆なければ自動登録
        try:
            ecs.describe_task_definition(taskDefinition=task_definition)
            logger.info(f"Task definition '{task_definition}' already exists.")
        except ecs.exceptions.ClientException:
            # 必要なロール情報を環境変数から取得
            execution_role_arn = os.environ.get("ECS_TASK_EXECUTION_ROLE_ARN")
            task_role_arn = os.environ.get("ECS_TASK_ROLE_ARN")
            if not execution_role_arn or not task_role_arn:
                logger.error("ECS_TASK_EXECUTION_ROLE_ARN または ECS_TASK_ROLE_ARN が未設定です")
                raise HTTPException(status_code=500, detail="ECS_TASK_EXECUTION_ROLE_ARN または ECS_TASK_ROLE_ARN が未設定です")
            # CloudWatch Logsのロググループを事前に作成（なければ）
            logs = boto3.client("logs", region_name=AWS_REGION)
            log_group_name = f"/ecs/{app_name}"
            try:
                resp = logs.create_log_group(logGroupName=log_group_name)
                logger.info(f"create_log_group response: {resp}")
                logger.info(f"Created log group: {log_group_name}")
            except logs.exceptions.ResourceAlreadyExistsException:
                logger.info(f"Log group already exists: {log_group_name}")
            except Exception as e:
                logger.exception(f"Exception during create_log_group: {e}")
            # ロググループ存在確認
            try:
                groups = logs.describe_log_groups(logGroupNamePrefix=log_group_name).get("logGroups", [])
                logger.info(f"describe_log_groups result: {groups}")
                if not any(g["logGroupName"] == log_group_name for g in groups):
                    logger.error(f"Log group {log_group_name} does NOT exist after create attempt!")
                    raise HTTPException(status_code=500, detail=f"Log group {log_group_name} does NOT exist after create attempt!")
            except Exception as e:
                logger.exception(f"Exception during describe_log_groups: {e}")
                raise HTTPException(status_code=500, detail=f"Exception during describe_log_groups: {e}")
            # タスク定義を自動登録
            ecs.register_task_definition(
                family=task_definition,
                networkMode="awsvpc",
                requiresCompatibilities=["FARGATE"],
                cpu="512",
                memory="1024",
                executionRoleArn=execution_role_arn,
                taskRoleArn=task_role_arn,
                containerDefinitions=[
                    {
                        "name": app_name,
                        "image": f"{ecr_url}:latest",
                        "portMappings": [
                            {
                                "containerPort": 7860,
                                "protocol": "tcp"
                            }
                        ],
                        "essential": True,
                        "environment": [],
                        "logConfiguration": {
                            "logDriver": "awslogs",
                            "options": {
                                "awslogs-group": log_group_name,
                                "awslogs-region": AWS_REGION,
                                "awslogs-stream-prefix": "ecs"
                            }
                        }
                    }
                ]
            )
            logger.info(f"Registered new task definition: {task_definition}")

        services = ecs.describe_services(cluster=CLUSTER_NAME, services=[app_name])["services"]
        service_status = None
        if services and "status" in services[0]:
            service_status = services[0]["status"]
        if not services or service_status != "ACTIVE":
            if services and service_status and service_status != "ACTIVE":
                logger.warning(f"Service {app_name} exists but status is {service_status}. Deleting before recreate.")
                try:
                    ecs.delete_service(cluster=CLUSTER_NAME, service=app_name, force=True)
                    logger.info(f"Deleted ECS service: {app_name}")
                except Exception as del_e:
                    logger.error(f"Failed to delete service {app_name}: {del_e}")
            logger.info(f"Creating ECS service: {app_name}")
            ecs.create_service(
                cluster=CLUSTER_NAME,
                serviceName=app_name,
                taskDefinition=task_definition,
                loadBalancers=[{
                    "targetGroupArn": tg_arn,
                    "containerName": app_name,
                    "containerPort": 7860
                }],
                desiredCount=1,
                launchType="FARGATE",
                networkConfiguration={
                    "awsvpcConfiguration": {
                        "subnets": subnets,
                        "securityGroups": security_groups,
                        "assignPublicIp": "ENABLED"
                    }
                }
            )
            logger.info(f"ECS service created: {app_name}")
        else:
            logger.info(f"Updating ECS service: {app_name}")
            try:
                ecs.update_service(
                    cluster=CLUSTER_NAME,
                    service=app_name,
                    forceNewDeployment=True
                )
                logger.info(f"ECS service updated: {app_name}")
            except Exception as update_e:
                logger.error(f"Failed to update service {app_name}: {update_e}")
                raise HTTPException(status_code=500, detail=f"Failed to update service: {update_e}")

        logger.info(f"Deployment for {app_name} completed successfully.")
        return {"status": "success", "message": f"{app_name} deployed!"}
    except Exception as e:
        logger.error(f"Exception during deployment: {e}")
        raise HTTPException(status_code=500, detail=str(e))