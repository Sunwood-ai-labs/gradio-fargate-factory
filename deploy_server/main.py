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
    # 新しいパラメータ追加
    cpu: str = "2048"  # デフォルトを大幅に増加
    memory: str = "4096"  # デフォルトを大幅に増加
    force_recreate: bool = False  # 強制再作成フラグ

@app.post("/deploy")
def deploy_app(req: DeployRequest):
    import tempfile
    import shutil

    app_name = req.app_name
    docker_context = req.docker_context
    dockerfile = req.dockerfile

    temp_dir = None
    deployed_url = None
    
    # git_repo_urlが指定されていればクローン
    if req.git_repo_url:
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
        elbv2 = boto3.client("elbv2", region_name=AWS_REGION)
        logs = boto3.client("logs", region_name=AWS_REGION)

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
                    "docker", "build", "--platform", "linux/amd64", "-t", f"{app_name}:latest", "-f", dockerfile, "."
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

        # ALBのVPC情報を取得
        listener_info = elbv2.describe_listeners(ListenerArns=[alb_listener_arn])
        lb_arn = listener_info["Listeners"][0]["LoadBalancerArn"]
        
        # ロードバランサーの詳細情報を取得
        lb_info = elbv2.describe_load_balancers(LoadBalancerArns=[lb_arn])
        alb_vpc_id = lb_info["LoadBalancers"][0]["VpcId"]
        alb_dns_name = lb_info["LoadBalancers"][0]["DNSName"]
        
        # プロトコルを決定
        protocol = "http"
        try:
            listeners = elbv2.describe_listeners(LoadBalancerArn=lb_arn)["Listeners"]
            has_https = any(listener["Port"] == 443 for listener in listeners)
            if has_https:
                protocol = "https"
        except Exception:
            protocol = "http"
        
        # ### <<< 修正 >>> ###
        # デプロイURLとGradioのルートパス、ヘルスチェックパスをここで一元的に定義
        base_path = alb_path.rstrip("/*").rstrip("/")  # "/myapp/*" -> "/myapp"
        deployed_url = f"{protocol}://{alb_dns_name}{base_path}"
        gradio_root_path = base_path # Gradioアプリに渡すルートパス
        health_check_path = "/" # Gradioのヘルスチェック用パス
        # health_check_path = "/health-check"
        
        logger.info(f"ALB DNS Name: {alb_dns_name}")
        logger.info(f"Target URL: {deployed_url}")
        logger.info(f"Gradio Root Path will be set to: {gradio_root_path}")
        logger.info(f"Target Group Health Check Path will be set to: {health_check_path}")


        # ターゲットグループの確認・作成・更新
        tg_name = f"{app_name}-tg"
        tg_arn = None
        
        try:
            existing_tgs = elbv2.describe_target_groups(Names=[tg_name])["TargetGroups"]
            tg_arn = existing_tgs[0]["TargetGroupArn"]
            logger.info(f"Using existing target group: {tg_name}")
            # ### <<< 追加 >>> ###
            # 既存ターゲットグループのヘルスチェック設定を更新
            elbv2.modify_target_group(
                TargetGroupArn=tg_arn,
                HealthCheckPath=health_check_path,
                HealthCheckIntervalSeconds=30, # 間隔を短くして早期復旧
                HealthCheckTimeoutSeconds=15, # タイムアウトも調整
                HealthyThresholdCount=2,
                UnhealthyThresholdCount=3, # 失敗回数を減らして早く切り離す
                Matcher={'HttpCode': '200'} # Gradioの/health-checkは200を返す
            )
            logger.info(f"Updated health check path for target group '{tg_name}' to '{health_check_path}'")

        except elbv2.exceptions.TargetGroupNotFoundException:
            # ターゲットグループを新規作成
            logger.info(f"Creating new target group: {tg_name}")
            # ### <<< 修正 >>> ###
            # ヘルスチェックパスを正しく設定
            tg = elbv2.create_target_group(
                Name=tg_name,
                Protocol="HTTP",
                Port=7860,
                VpcId=alb_vpc_id,
                TargetType="ip",
                HealthCheckPath=health_check_path, # 正しいパスを設定
                HealthCheckProtocol="HTTP",
                HealthCheckIntervalSeconds=30,
                HealthCheckTimeoutSeconds=15,
                HealthyThresholdCount=2,
                UnhealthyThresholdCount=3,
                Matcher={'HttpCode': '200'} # 200のみを正常とみなす
            )
            tg_arn = tg["TargetGroups"][0]["TargetGroupArn"]
            logger.info(f"Created target group: {tg_name}")

        # ALBルールの確認・作成
        rules = elbv2.describe_rules(ListenerArn=alb_listener_arn)["Rules"]
        rule_exists = False
        for rule in rules:
            for cond in rule.get("Conditions", []):
                if cond.get("Field") == "path-pattern" and alb_path in cond.get("Values", []):
                    rule_exists = True
                    # ### <<< 追加 >>> ###
                    # ルールが既にあれば、転送先TGが正しいか確認・修正する
                    is_correct_tg = False
                    for action in rule.get("Actions", []):
                        if action.get("TargetGroupArn") == tg_arn:
                            is_correct_tg = True
                            break
                    if not is_correct_tg:
                        logger.warning(f"Rule for path '{alb_path}' exists but points to wrong TG. Modifying...")
                        elbv2.modify_rule(
                            RuleArn=rule['RuleArn'],
                            Actions=[{'Type': 'forward', 'TargetGroupArn': tg_arn}]
                        )
                    break
            if rule_exists:
                break
        
        if not rule_exists:
            existing_priorities = [int(rule.get("Priority", 0)) for rule in rules if rule.get("Priority") != "default"]
            next_priority = max(existing_priorities) + 1 if existing_priorities else 100
            
            elbv2.create_rule(
                ListenerArn=alb_listener_arn,
                Priority=next_priority,
                Conditions=[{"Field": "path-pattern", "Values": [alb_path]}],
                Actions=[{"Type": "forward", "TargetGroupArn": tg_arn}]
            )
            logger.info(f"Created ALB rule with priority {next_priority}")

        # ECSタスク定義の設定
        task_definition_family = app_name # タスク定義ファミリーはアプリ名と一致させる
        execution_role_arn = os.environ.get("ECS_TASK_EXECUTION_ROLE_ARN")
        task_role_arn = os.environ.get("ECS_TASK_ROLE_ARN")
        
        if not execution_role_arn or not task_role_arn:
            raise HTTPException(status_code=500, detail="ECS role ARNs not configured")

        # CloudWatch Logsの確認
        log_group_name = f"/ecs/{app_name}"
        try:
            logs.create_log_group(logGroupName=log_group_name)
            logger.info(f"Created log group: {log_group_name}")
        except logs.exceptions.ResourceAlreadyExistsException:
            logger.info(f"Log group already exists: {log_group_name}")

        # 新しいタスク定義を登録
        logger.info(f"Registering task definition with CPU: {req.cpu}, Memory: {req.memory}")
        ecs.register_task_definition(
            family=task_definition_family,
            networkMode="awsvpc",
            requiresCompatibilities=["FARGATE"],
            cpu=req.cpu,
            memory=req.memory,
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
                    # ### <<< 修正 >>> ###
                    # 環境変数にGRADIO_ROOT_PATHを追加
                    "environment": [
                        {"name": "GRADIO_SERVER_NAME", "value": "0.0.0.0"},
                        {"name": "GRADIO_SERVER_PORT", "value": "7860"},
                        {"name": "GRADIO_ROOT_PATH", "value": gradio_root_path}
                    ],
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

        # サブネット設定
        subnets_env = os.environ.get("SUBNETS") or os.environ.get("PUBLIC_SUBNET_IDS") or os.environ.get("PRIVATE_SUBNET_IDS") or ""
        subnets = [s.strip() for s in subnets_env.split(",") if s.strip()]
        security_groups = [s.strip() for s in os.environ.get("SECURITY_GROUPS", "").split(",") if s.strip()]

        # ECSサービスの処理
        services = ecs.describe_services(cluster=CLUSTER_NAME, services=[app_name])["services"]
        
        if services and services[0]["status"] == "ACTIVE" and not req.force_recreate:
            # 既存サービスを更新
            logger.info(f"Updating existing ECS service: {app_name}")
            try:
                ecs.update_service(
                    cluster=CLUSTER_NAME,
                    service=app_name,
                    taskDefinition=task_definition_family, # ### <<< 修正 >>> ### family名を渡す
                    enableExecuteCommand=True, 
                    forceNewDeployment=True
                )
                logger.info(f"Successfully updated service: {app_name}")
                deployment_type = "update"
                
            except Exception as update_e:
                logger.error(f"Failed to update service: {update_e}")
                raise HTTPException(status_code=500, detail=f"Service update failed: {update_e}")
                
        else:
            # 新しいサービスを作成
            if services and req.force_recreate:
                logger.info(f"Force recreate requested - deleting existing service")
                try:
                    ecs.delete_service(cluster=CLUSTER_NAME, service=app_name, force=True)
                    logger.info(f"Deleted existing service for recreation")
                    
                    # 削除完了を待機
                    import time
                    for i in range(30):
                        time.sleep(10)
                        try:
                            remaining = ecs.describe_services(cluster=CLUSTER_NAME, services=[app_name])["services"]
                            if not remaining or remaining[0]["status"] == "INACTIVE":
                                logger.info(f"Service deletion completed after {(i+1)*10} seconds")
                                break
                        except:
                            break
                except Exception as del_e:
                    logger.warning(f"Failed to delete service: {del_e}")
            
            logger.info(f"Creating new ECS service: {app_name}")
            try:
                ecs.create_service(
                    cluster=CLUSTER_NAME,
                    serviceName=app_name,
                    taskDefinition=task_definition_family, # ### <<< 修正 >>> ### family名を渡す
                    enableExecuteCommand=True,
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
                            "assignPublicIp": "ENABLED" # 開発・検証用途としてENABLEDのまま
                        }
                    },
                    healthCheckGracePeriodSeconds=300 # ヘルスチェックの猶予期間
                )
                logger.info(f"Successfully created service: {app_name}")
                deployment_type = "create"
                
            except Exception as create_e:
                logger.error(f"Failed to create service: {create_e}")
                raise HTTPException(status_code=500, detail=f"Service creation failed: {create_e}")

        # 成功ログとレスポンス
        logger.info(f"🚀 Deployment completed: {deployed_url}")
        logger.info(f"💾 Resources: CPU={req.cpu}, Memory={req.memory}")
        logger.info(f"⏱️  Allow 5-10 minutes for service to become healthy")
        
        return {
            "status": "success",
            "message": f"{app_name} deployed successfully!",
            "deployed_url": deployed_url,
            "alb_dns_name": alb_dns_name,
            "alb_path": alb_path,
            "app_name": app_name,
            "protocol": protocol,
            "cpu": req.cpu,
            "memory": req.memory,
            "deployment_type": deployment_type,
            "estimated_ready_time": "5-10 minutes"
        }
        
    except Exception as e:
        logger.error(f"Deployment failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # クリーンアップ
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                logger.info(f"Cleaned up: {temp_dir}")
            except Exception as cleanup_e:
                logger.warning(f"Cleanup failed: {cleanup_e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
