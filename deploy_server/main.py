from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import subprocess
import boto3
from loguru import logger
import os
from dotenv import load_dotenv
from botocore.exceptions import ClientError

load_dotenv()

logger.add("deploy_server.log", rotation="1 MB")
app = FastAPI()

AWS_REGION = "ap-northeast-1"
CLUSTER_NAME = os.getenv("ECS_CLUSTER_NAME", "gradio-ecs-cluster")

class DeployRequest(BaseModel):
    app_name: str
    docker_context: str = "./"
    dockerfile: str = "Dockerfile"
    alb_path: str  # 例: "/image-filter/*"
    git_repo_url: str | None = None
    cpu: str = "2048"
    memory: str = "4096"
    force_recreate: bool = False

def ensure_security_group_rules():
    """ECSセキュリティグループに必要なルールを追加"""
    try:
        ec2 = boto3.client("ec2", region_name=AWS_REGION)
        
        ecs_sg_id = os.getenv("ECS_SECURITY_GROUP_ID")
        alb_sg_id = os.getenv("ALB_SECURITY_GROUP_ID")
        
        if not ecs_sg_id or not alb_sg_id:
            logger.warning("Security Group IDs not configured - skipping rule setup")
            return
        
        # ALBからECSへのポート7860通信を許可
        try:
            ec2.authorize_security_group_ingress(
                GroupId=ecs_sg_id,
                IpPermissions=[
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 7860,
                        'ToPort': 7860,
                        'UserIdGroupPairs': [
                            {
                                'GroupId': alb_sg_id,
                                'Description': 'ALB to ECS Gradio port'
                            }
                        ]
                    }
                ]
            )
            logger.info(f"Added port 7860 rule: ALB ({alb_sg_id}) -> ECS ({ecs_sg_id})")
        except ClientError as e:
            if 'InvalidPermission.Duplicate' in str(e):
                logger.info("Port 7860 ALB->ECS rule already exists")
            else:
                logger.error(f"Failed to add ALB->ECS rule: {e}")
        
        # ECS自己参照でのポート7860も追加
        try:
            ec2.authorize_security_group_ingress(
                GroupId=ecs_sg_id,
                IpPermissions=[
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 7860,
                        'ToPort': 7860,
                        'UserIdGroupPairs': [
                            {
                                'GroupId': ecs_sg_id,
                                'Description': 'ECS self-reference for Gradio'
                            }
                        ]
                    }
                ]
            )
            logger.info(f"Added port 7860 self-reference rule for ECS ({ecs_sg_id})")
        except ClientError as e:
            if 'InvalidPermission.Duplicate' in str(e):
                logger.info("Port 7860 self-reference rule already exists")
            else:
                logger.error(f"Failed to add self-reference rule: {e}")
                
    except Exception as e:
        logger.error(f"Error setting up security group rules: {e}")
        # セキュリティグループの設定は失敗してもデプロイを続行

@app.post("/deploy")
def deploy_app(req: DeployRequest):
    import tempfile
    import shutil

    app_name = req.app_name
    docker_context = req.docker_context
    dockerfile = req.dockerfile

    temp_dir = None
    deployed_url = None
    
    # セキュリティグループルールの確認・追加
    ensure_security_group_rules()
    
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

        # ALB設定
        alb_listener_arn = os.getenv("ALB_LISTENER_ARN")
        alb_dns_name = os.getenv("ALB_DNS_NAME")
        alb_vpc_id = os.getenv("VPC_ID")
        
        if not alb_listener_arn or not alb_dns_name or not alb_vpc_id:
            raise Exception("ALB environment variables not configured")
        
        alb_path = req.alb_path
        
        # プロトコル決定
        protocol = "http"
        try:
            alb_arn = os.getenv("ALB_ARN")
            if alb_arn:
                listeners = elbv2.describe_listeners(LoadBalancerArn=alb_arn)["Listeners"]
                has_https = any(listener["Port"] == 443 for listener in listeners)
                if has_https:
                    protocol = "https"
        except Exception:
            protocol = "http"
        
        # URL設定
        base_path = alb_path.rstrip("/*").rstrip("/")
        deployed_url = f"{protocol}://{alb_dns_name}{base_path}"
        gradio_root_path = base_path
        health_check_path = "/"
        
        logger.info(f"ALB DNS Name: {alb_dns_name}")
        logger.info(f"Target URL: {deployed_url}")
        logger.info(f"Gradio Root Path: {gradio_root_path}")
        logger.info(f"Health Check Path: {health_check_path}")

        # ターゲットグループの確認・作成・更新
        tg_name = f"{app_name}-tg"
        tg_arn = None
        
        try:
            existing_tgs = elbv2.describe_target_groups(Names=[tg_name])["TargetGroups"]
            tg_arn = existing_tgs[0]["TargetGroupArn"]
            logger.info(f"Using existing target group: {tg_name}")
            
            # ヘルスチェック設定を最適化
            elbv2.modify_target_group(
                TargetGroupArn=tg_arn,
                HealthCheckPath=health_check_path,
                HealthCheckIntervalSeconds=30,
                HealthCheckTimeoutSeconds=5,  # タイムアウトを短縮
                HealthyThresholdCount=2,
                UnhealthyThresholdCount=3,
                Matcher={'HttpCode': '200'}
            )
            logger.info(f"Updated health check settings for target group '{tg_name}'")

        except elbv2.exceptions.TargetGroupNotFoundException:
            logger.info(f"Creating new target group: {tg_name}")
            tg = elbv2.create_target_group(
                Name=tg_name,
                Protocol="HTTP",
                Port=7860,
                VpcId=alb_vpc_id,
                TargetType="ip",
                HealthCheckPath=health_check_path,
                HealthCheckProtocol="HTTP",
                HealthCheckIntervalSeconds=30,
                HealthCheckTimeoutSeconds=5,
                HealthyThresholdCount=2,
                UnhealthyThresholdCount=3,
                Matcher={'HttpCode': '200'}
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
                    # ルールの転送先TGが正しいか確認・修正
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
        task_definition_family = app_name
        execution_role_arn = os.getenv("ECS_TASK_EXECUTION_ROLE_ARN")
        task_role_arn = os.getenv("ECS_TASK_ROLE_ARN")
        
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

        # サブネット・セキュリティグループ設定
        subnets = [s.strip() for s in os.getenv("SUBNETS", "").split(",") if s.strip()]
        security_groups = [s.strip() for s in os.getenv("SECURITY_GROUPS", "").split(",") if s.strip()]

        # ECSサービスの処理
        services = ecs.describe_services(cluster=CLUSTER_NAME, services=[app_name])["services"]
        
        if services and services[0]["status"] == "ACTIVE" and not req.force_recreate:
            # 既存サービスを更新
            logger.info(f"Updating existing ECS service: {app_name}")
            try:
                ecs.update_service(
                    cluster=CLUSTER_NAME,
                    service=app_name,
                    taskDefinition=task_definition_family,
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
                    taskDefinition=task_definition_family,
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
                            "assignPublicIp": "ENABLED"
                        }
                    },
                    healthCheckGracePeriodSeconds=300
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
    uvicorn.run(app, host="0.0.0.0", port=8002)