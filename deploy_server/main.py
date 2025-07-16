from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import subprocess
import boto3
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

AWS_REGION = "ap-northeast-1"
CLUSTER_NAME = "gradio-ecs-cluster"

class DeployRequest(BaseModel):
    app_name: str
    docker_context: str = "./"  # Dockerfileのあるディレクトリ
    dockerfile: str = "Dockerfile"  # Dockerfile名（省略可）
    alb_path: str  # 例: "/image-filter/*"

@app.post("/deploy")
def deploy_app(req: DeployRequest):
    app_name = req.app_name
    docker_context = req.docker_context
    dockerfile = req.dockerfile

    try:
        # AWS情報取得
        sts = boto3.client("sts", region_name=AWS_REGION)
        account_id = sts.get_caller_identity()["Account"]
        ecr = boto3.client("ecr", region_name=AWS_REGION)
        ecs = boto3.client("ecs", region_name=AWS_REGION)

        # ECRリポジトリURL取得
        ecr_url = ecr.describe_repositories(repositoryNames=[app_name])["repositories"][0]["repositoryUri"]

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
        subprocess.check_call([
            "docker", "build", "-t", f"{app_name}:latest", "-f", dockerfile, docker_context
        ])
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

        # ECSサービスforce-new-deployment
        ecs.update_service(
            cluster=CLUSTER_NAME,
            service=app_name,
            forceNewDeployment=True
        )

        # ECSサービスforce-new-deployment
        ecs.update_service(
            cluster=CLUSTER_NAME,
            service=app_name,
            forceNewDeployment=True
        )

        return {"status": "success", "message": f"{app_name} deployed!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))