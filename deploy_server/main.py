import os
import subprocess
import boto3
from fastapi import FastAPI, HTTPException
from loguru import logger

from models.deploy import DeployRequest
from utils.common import (
    load_terraform_outputs,
    get_config_value,
    ensure_security_group_rules,
    AWS_REGION,
    CLUSTER_NAME,
    TERRAFORM_STATE_PATH,
)

logger.add("deploy_server.log", rotation="1 MB")
app = FastAPI()

@app.get("/config")
def get_current_config():
    """現在の設定情報を確認するためのエンドポイント"""
    try:
        tf_outputs = load_terraform_outputs()
        config = {
            "aws_region": AWS_REGION,
            "cluster_name": CLUSTER_NAME,
            "terraform_state_path": TERRAFORM_STATE_PATH,
            "terraform_outputs_available": list(tf_outputs.keys()),
            "resolved_config": {
                "alb_arn": get_config_value("ALB_ARN", "alb_arn", "not_configured"),
                "alb_dns_name": get_config_value("ALB_DNS_NAME", "alb_dns_name", "not_configured"),
                "alb_listener_arn": get_config_value("ALB_LISTENER_ARN", "alb_listener_arn", "not_configured"),
                "vpc_id": get_config_value("VPC_ID", "vpc_id", "not_configured"),
                "ecs_cluster_name": get_config_value("ECS_CLUSTER_NAME", "ecs_cluster_name", CLUSTER_NAME),
                "ecs_task_execution_role_arn": get_config_value("ECS_TASK_EXECUTION_ROLE_ARN", "ecs_task_execution_role_arn", "not_configured"),
                "ecs_task_role_arn": get_config_value("ECS_TASK_ROLE_ARN", "ecs_task_role_arn", "not_configured"),
            }
        }
        return config
    except Exception as e:
        return {"error": str(e)}

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

        # ALB設定 - Terraform outputsと環境変数から取得
        alb_listener_arn = get_config_value("ALB_LISTENER_ARN", "alb_listener_arn")
        alb_dns_name = get_config_value("ALB_DNS_NAME", "alb_dns_name")
        alb_vpc_id = get_config_value("VPC_ID", "vpc_id")
        
        alb_path = req.alb_path
        
        # プロトコル決定
        protocol = "http"
        try:
            alb_arn = get_config_value("ALB_ARN", "alb_arn")
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
                HealthCheckTimeoutSeconds=5,
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

        # ECSタスク定義の設定 - Terraform outputsから取得
        task_definition_family = app_name
        execution_role_arn = get_config_value("ECS_TASK_EXECUTION_ROLE_ARN", "ecs_task_execution_role_arn")
        task_role_arn = get_config_value("ECS_TASK_ROLE_ARN", "ecs_task_role_arn")

        # CloudWatch Logsの確認
        log_group_name = f"/ecs/{app_name}"
        try:
            logs.create_log_group(logGroupName=log_group_name)
            logger.info(f"Created log group: {log_group_name}")
        except logs.exceptions.ResourceAlreadyExistsException:
            logger.info(f"Log group already exists: {log_group_name}")

        # 新しいタスク定義を登録
        from utils.aws import register_task_definition, update_ecs_service, delete_ecs_service, create_ecs_service
        register_task_definition(
            ecs, app_name, req, ecr_url, gradio_root_path, log_group_name, execution_role_arn, task_role_arn
        )

        # サブネット・セキュリティグループ設定 - Terraform outputsと環境変数から取得
        # SUBNETSが設定されていればそれを使用、なければpublic_subnet_idsから取得
        subnets_str = get_config_value("SUBNETS", "private_subnet_ids", None)
        if not subnets_str:
            # Terraform outputからpublic_subnet_idsを取得
            tf_outputs = load_terraform_outputs()
            public_subnets = tf_outputs.get("public_subnet_ids", [])
            if isinstance(public_subnets, list):
                subnets_str = ",".join(public_subnets)
            else:
                subnets_str = str(public_subnets)
        
        if isinstance(subnets_str, list):
            subnets = [s.strip() for s in subnets_str if s.strip()]
        else:
            subnets = [s.strip() for s in str(subnets_str).split(",") if s.strip()]
        
        # セキュリティグループも同様に取得
        security_groups_str = get_config_value("SECURITY_GROUPS", "ecs_security_group_id", None)
        if not security_groups_str:
            # ECSタスク用のセキュリティグループIDを取得
            ecs_sg_id = get_config_value("ECS_SECURITY_GROUP_ID", "ecs_security_group_id", None)
            if ecs_sg_id:
                security_groups_str = ecs_sg_id
        
        if isinstance(security_groups_str, list):
            security_groups = [s.strip() for s in security_groups_str if s.strip()]
        else:
            security_groups = [s.strip() for s in str(security_groups_str).split(",") if s.strip()]

        # ECSサービスの処理
        services = ecs.describe_services(cluster=CLUSTER_NAME, services=[app_name])["services"]
        
        if services and services[0]["status"] == "ACTIVE" and not req.force_recreate:
            # 既存サービスを更新
            logger.info(f"Updating existing ECS service: {app_name}")
            deployment_type = update_ecs_service(ecs, app_name, task_definition_family)
                
        else:
            # 新しいサービスを作成
            if services and req.force_recreate:
                deleted = delete_ecs_service(ecs, app_name)
                if deleted:
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
            
            deployment_type = create_ecs_service(
                ecs, app_name, task_definition_family, tg_arn, subnets, security_groups
            )

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