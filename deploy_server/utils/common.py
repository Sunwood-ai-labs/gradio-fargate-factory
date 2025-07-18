import os
import json
from pathlib import Path
from loguru import logger
import boto3
from dotenv import load_dotenv
from botocore.exceptions import ClientError

from pathlib import Path

# プロジェクトルートとdeploy_server直下の .env を両方ロード
from loguru import logger

root_env_path = Path(__file__).parent.parent.parent / ".env"
deploy_env_path = Path(__file__).parent.parent / ".env"

root_env_loaded = load_dotenv(dotenv_path=root_env_path, override=False)
deploy_env_loaded = load_dotenv(dotenv_path=deploy_env_path, override=True)

if root_env_path.exists():
    logger.debug(f"Loaded .env from: {root_env_path.resolve()}")
else:
    logger.debug(f".env not found at: {root_env_path.resolve()}")

if deploy_env_path.exists():
    logger.debug(f"Loaded .env from: {deploy_env_path.resolve()}")
else:
    logger.debug(f".env not found at: {deploy_env_path.resolve()}")

# .envの内容をデバッグ出力
logger.debug(f"ENV: TERRAFORM_STATE_PATH={os.environ.get('TERRAFORM_STATE_PATH')}")
logger.debug(f"ENV: AWS_REGION={os.environ.get('AWS_REGION')}")
logger.debug(f"ENV: ECS_CLUSTER_NAME={os.environ.get('ECS_CLUSTER_NAME')}")
logger.debug(f"ENV: CLONE_BASE_DIR={os.environ.get('CLONE_BASE_DIR')}")

AWS_REGION = os.getenv("AWS_REGION", "ap-northeast-1")
CLUSTER_NAME = os.getenv("ECS_CLUSTER_NAME", "gradio-ecs-cluster")
TERRAFORM_STATE_PATH = os.getenv(
    "TERRAFORM_STATE_PATH",
    "terraform/environments/base-infrastructure/terraform.tfstate"
)

def load_terraform_outputs():
    """Terraform状態ファイルからoutputを読み込み"""
    try:
        # 絶対パスと相対パスの両方に対応
        if os.path.isabs(TERRAFORM_STATE_PATH):
            # .envで絶対パスが指定されていればそのまま使う
            state_file_path = Path(TERRAFORM_STATE_PATH).resolve()
            logger.debug(f"Using absolute path for terraform state: {state_file_path}")
        else:
            # 相対パスの場合、main.pyの親（プロジェクトルート）からの相対パス
            project_root = Path(__file__).resolve().parent.parent
            state_file_path = (project_root / TERRAFORM_STATE_PATH).resolve()
            logger.debug(f"Using relative path for terraform state: {state_file_path}")
        
        if not state_file_path.exists():
            logger.warning(f"Terraform state file not found at {state_file_path}")
            return {}
        
        with open(state_file_path, 'r') as f:
            state_data = json.load(f)
        
        outputs = {}
        if 'outputs' in state_data:
            for key, output in state_data['outputs'].items():
                outputs[key] = output['value']
        
        logger.info(f"Loaded Terraform outputs from {state_file_path}")
        logger.debug(f"Available outputs: {list(outputs.keys())}")
        return outputs
        
    except Exception as e:
        logger.error(f"Error loading Terraform outputs: {e}")
        return {}

def get_config_value(env_key: str, tf_output_key: str = None, default: str = None):
    """環境変数 > Terraform output > デフォルト値 の優先順位で設定値を取得"""
    env_value = os.getenv(env_key)
    if env_value:
        return env_value
    
    if tf_output_key:
        tf_outputs = load_terraform_outputs()
        tf_value = tf_outputs.get(tf_output_key)
        if tf_value:
            return tf_value
    
    if default is not None:
        return default
    
    raise ValueError(f"Configuration value not found: env_key={env_key}, tf_output_key={tf_output_key}")

def ensure_security_group_rules():
    """ECSセキュリティグループに必要なルールを追加"""
    try:
        ec2 = boto3.client("ec2", region_name=AWS_REGION)
        
        # セキュリティグループIDを取得
        ecs_sg_id = get_config_value("ECS_SECURITY_GROUP_ID", "ecs_security_group_id", None)
        alb_sg_id = get_config_value("ALB_SECURITY_GROUP_ID", "alb_security_group_id", None)
        
        if not ecs_sg_id:
            logger.warning("ECS Security Group ID not found - checking Terraform outputs for ecs_tasks security group")
            tf_outputs = load_terraform_outputs()
            # aws_security_group.ecs_tasksのIDを探す
            if 'resources' in load_terraform_outputs():
                # この場合は別の方法でSGを見つける必要がある
                pass
        
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