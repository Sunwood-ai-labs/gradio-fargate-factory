#!/bin/bash
# scripts/create-new-app.sh
# 新しいGradioアプリのスケルトンを作成

set -e

# 設定
PROJECT_NAME="gradio-ecs"
ENVIRONMENT="dev"
AWS_REGION="ap-northeast-1"

# 色付きログ出力
log_info() { echo -e "\033[32m[INFO]\033[0m $1"; }
log_error() { echo -e "\033[31m[ERROR]\033[0m $1"; }
log_warn() { echo -e "\033[33m[WARN]\033[0m $1"; }

# 使用方法
usage() {
    echo "使用方法: $0 <app_name> [app_path] [port]"
    echo ""
    echo "引数:"
    echo "  app_name   アプリケーション名（必須）"
    echo "  app_path   ALBパスパターン（デフォルト: /<app_name>/*）"
    echo "  port       アプリポート（デフォルト: 7860）"
    echo ""
    echo "例:"
    echo "  $0 my-chatbot"
    echo "  $0 image-classifier /classifier/* 8080"
}

# アプリディレクトリ作成
create_app_structure() {
    local app_name=$1
    local app_path=${2:-"/${app_name}/*"}
    local app_port=${3:-7860}
    local app_dir="apps/${app_name}"
    
    log_info "Creating app structure for: $app_name"
    
    # ディレクトリ作成
    mkdir -p "$app_dir/src"
    mkdir -p "$app_dir/terraform"
    
    # Gradioアプリケーション作成
    cat > "$app_dir/src/app.py" << EOF
import gradio as gr
import os

def process_text(text):
    """テキスト処理のサンプル関数 - このアプリ固有の処理に変更してください"""
    return f"${app_name} processed: {text.upper()}"

def main():
    # Gradioインターフェース作成
    interface = gr.Interface(
        fn=process_text,
        inputs=gr.Textbox(label="入力テキスト", placeholder="何か入力してください"),
        outputs=gr.Textbox(label="処理結果"),
        title="${app_name}",
        description="このアプリは ${app_name} です。app.pyを編集してカスタマイズしてください。"
    )
    
    # サーバー設定
    port = int(os.environ.get('PORT', ${app_port}))
    
    interface.launch(
        server_name="0.0.0.0",  # Docker環境で必須
        server_port=port,
        share=False,
        debug=False
    )

if __name__ == "__main__":
    main()
EOF

    # requirements.txt作成
    cat > "$app_dir/src/requirements.txt" << EOF
gradio==4.25.0
pillow
numpy
pandas
requests
EOF

    # Dockerfile作成
    cat > "$app_dir/src/Dockerfile" << EOF
FROM python:3.11-slim

WORKDIR /app

# 必要なシステムパッケージをインストール
RUN apt-get update && apt-get install -y \\
    curl \\
    && rm -rf /var/lib/apt/lists/*

# 依存関係をコピーしてインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードをコピー
COPY app.py .

# ポートを公開
EXPOSE ${app_port}

# 環境変数設定
ENV PYTHONUNBUFFERED=1
ENV GRADIO_SERVER_NAME=0.0.0.0
ENV PORT=${app_port}

# ヘルスチェック
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \\
    CMD curl -f http://localhost:${app_port}/ || exit 1

# アプリケーション実行
CMD ["python", "app.py"]
EOF

    # Terraform設定作成
    create_terraform_config "$app_name" "$app_path" "$app_port" "$app_dir"
    
    # デプロイスクリプト作成
    create_deploy_script "$app_name" "$app_dir"
    
    log_info "App structure created successfully!"
    log_info "Next steps:"
    log_info "1. Edit $app_dir/src/app.py to implement your Gradio app"
    log_info "2. cd $app_dir && ./deploy.sh"
}

# Terraform設定作成
create_terraform_config() {
    local app_name=$1
    local app_path=$2
    local app_port=$3
    local app_dir=$4
    
    # 優先度を自動計算（既存アプリ数+100）
    local priority=$(($(find apps -maxdepth 1 -type d | wc -l) + 90))
    
    # main.tf作成
    cat > "$app_dir/terraform/main.tf" << EOF
terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  
  backend "s3" {
    bucket = "your-terraform-state-bucket"
    key    = "gradio-ecs/apps/${app_name}/terraform.tfstate"
    region = "${AWS_REGION}"
  }
}

provider "aws" {
  region = var.aws_region
  
  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      App         = "${app_name}"
      ManagedBy   = "Terraform"
    }
  }
}

# 基盤インフラからの情報取得
data "terraform_remote_state" "base" {
  backend = "s3"
  config = {
    bucket = "your-terraform-state-bucket"
    key    = "gradio-ecs/base-infrastructure/terraform.tfstate"
    region = "${AWS_REGION}"
  }
}

# Gradioアプリモジュール
module "gradio_app" {
  source = "../../terraform/modules/gradio-app"
  
  app_name     = "${app_name}"
  app_path     = "${app_path}"
  app_port     = ${app_port}
  priority     = ${priority}
  
  project_name = var.project_name
  environment  = var.environment
  aws_region   = var.aws_region
  
  # 基盤インフラからの参照
  vpc_id                       = data.terraform_remote_state.base.outputs.vpc_id
  private_subnet_ids           = data.terraform_remote_state.base.outputs.private_subnet_ids
  ecs_cluster_id              = data.terraform_remote_state.base.outputs.ecs_cluster_id
  alb_listener_arn            = data.terraform_remote_state.base.outputs.alb_listener_arn
  ecs_security_group_id       = data.terraform_remote_state.base.outputs.ecs_security_group_id
  ecs_task_execution_role_arn = data.terraform_remote_state.base.outputs.ecs_task_execution_role_arn
  ecs_task_role_arn          = data.terraform_remote_state.base.outputs.ecs_task_role_arn
}
EOF

    # variables.tf作成
    cat > "$app_dir/terraform/variables.tf" << EOF
variable "project_name" {
  description = "プロジェクト名"
  type        = string
  default     = "${PROJECT_NAME}"
}

variable "environment" {
  description = "環境名"
  type        = string
  default     = "${ENVIRONMENT}"
}

variable "aws_region" {
  description = "AWSリージョン"
  type        = string
  default     = "${AWS_REGION}"
}
EOF

    # terraform.tfvars作成
    cat > "$app_dir/terraform/terraform.tfvars" << EOF
project_name = "${PROJECT_NAME}"
environment  = "${ENVIRONMENT}"
aws_region   = "${AWS_REGION}"
EOF

    # outputs.tf作成
    cat > "$app_dir/terraform/outputs.tf" << EOF
output "ecr_repository_url" {
  description = "ECRリポジトリURL"
  value       = module.gradio_app.ecr_repository_url
}

output "app_url_path" {
  description = "アプリアクセスパス"
  value       = module.gradio_app.app_url_path
}

output "ecs_service_name" {
  description = "ECSサービス名"
  value       = module.gradio_app.ecs_service_name
}
EOF
}

# デプロイスクリプト作成
create_deploy_script() {
    local app_name=$1
    local app_dir=$2
    
    cat > "$app_dir/deploy.sh" << 'DEPLOY_SCRIPT_EOF'
#!/bin/bash
# アプリ専用デプロイスクリプト

set -e

# 現在のディレクトリからアプリ名を取得
APP_NAME=$(basename "$(pwd)")
APP_DIR=$(pwd)
PROJECT_ROOT=$(cd ../../ && pwd)

# 設定
AWS_REGION="ap-northeast-1"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# 色付きログ出力
log_info() { echo -e "\033[32m[INFO]\033[0m $1"; }
log_error() { echo -e "\033[31m[ERROR]\033[0m $1"; }
log_warn() { echo -e "\033[33m[WARN]\033[0m $1"; }

# ECRログイン
ecr_login() {
    log_info "ECRにログインしています..."
    aws ecr get-login-password --region $AWS_REGION | \
        docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com
}

# Dockerイメージビルド・プッシュ
build_and_push() {
    log_info "Dockerイメージをビルドしています..."
    
    cd src
    
    # イメージビルド
    docker build -t $APP_NAME:latest .
    
    # ECRリポジトリURL取得
    ECR_URL=$(terraform -chdir=../terraform output -raw ecr_repository_url 2>/dev/null || echo "")
    
    if [ -z "$ECR_URL" ]; then
        log_error "ECRリポジトリURLが取得できません。先にTerraformでインフラを作成してください。"
        exit 1
    fi
    
    # タグ付け
    docker tag $APP_NAME:latest $ECR_URL:latest
    
    # プッシュ
    log_info "ECRにプッシュしています..."
    docker push $ECR_URL:latest
    
    cd ..
}

# Terraformでインフラ作成・更新
deploy_infrastructure() {
    log_info "Terraformでインフラを作成・更新しています..."
    
    cd terraform
    
    terraform init
    terraform plan
    terraform apply -auto-approve
    
    cd ..
}

# ECSサービス更新
update_service() {
    log_info "ECSサービスを更新しています..."
    
    # ECSサービス名を取得
    SERVICE_NAME=$(terraform -chdir=terraform output -raw ecs_service_name)
    CLUSTER_NAME="gradio-ecs-cluster"  # 基盤インフラで定義したクラスター名
    
    # サービス強制更新
    aws ecs update-service \
        --cluster $CLUSTER_NAME \
        --service $SERVICE_NAME \
        --force-new-deployment \
        --region $AWS_REGION
    
    log_info "デプロイが開始されました。サービスの状態を確認しています..."
    
    # デプロイ完了まで待機
    aws ecs wait services-stable \
        --cluster $CLUSTER_NAME \
        --services $SERVICE_NAME \
        --region $AWS_REGION
    
    log_info "デプロイが完了しました！"
}

# アプリURL表示
show_app_info() {
    log_info "=== デプロイ完了 ==="
    
    # ALB DNS名取得（基盤インフラから）
    ALB_DNS=$(aws elbv2 describe-load-balancers \
        --names "gradio-ecs-alb" \
        --query 'LoadBalancers[0].DNSName' \
        --output text \
        --region $AWS_REGION 2>/dev/null || echo "")
    
    if [ -n "$ALB_DNS" ]; then
        APP_PATH=$(terraform -chdir=terraform output -raw app_url_path | sed 's/\*$//')
        echo ""
        log_info "アプリケーションURL: http://$ALB_DNS$APP_PATH"
        echo ""
    fi
    
    log_info "ログ確認: aws logs tail /ecs/$APP_NAME --follow --region $AWS_REGION"
}

# メイン処理
main() {
    log_info "=== $APP_NAME デプロイ開始 ==="
    
    # ECRログイン
    ecr_login
    
    # インフラ作成・更新
    deploy_infrastructure
    
    # イメージビルド・プッシュ
    build_and_push
    
    # サービス更新
    update_service
    
    # 結果表示
    show_app_info
}

# 実行
main "$@"
DEPLOY_SCRIPT_EOF

    chmod +x "$app_dir/deploy.sh"
}

# メイン処理
main() {
    if [ $# -eq 0 ]; then
        usage
        exit 1
    fi
    
    local app_name=$1
    local app_path=$2
    local app_port=$3
    
    # アプリ名検証
    if [[ ! "$app_name" =~ ^[a-z0-9][a-z0-9-]*[a-z0-9]$ ]]; then
        log_error "アプリ名は英数字とハイフンのみ使用できます（最初と最後は英数字）"
        exit 1
    fi
    
    # 既存チェック
    if [ -d "apps/$app_name" ]; then
        log_error "アプリ '$app_name' は既に存在します"
        exit 1
    fi
    
    # アプリ作成
    create_app_structure "$app_name" "$app_path" "$app_port"
}

main "$@"

# scripts/setup-infrastructure.sh
#!/bin/bash
# 基盤インフラ構築スクリプト

set -e

log_info() { echo -e "\033[32m[INFO]\033[0m $1"; }
log_error() { echo -e "\033[31m[ERROR]\033[0m $1"; }

# S3バケット存在チェック・作成
setup_terraform_backend() {
    local bucket_name="your-terraform-state-bucket"  # 適切な名前に変更してください
    local region="ap-northeast-1"
    
    log_info "Terraformバックエンド用S3バケットをセットアップしています..."
    
    # バケット存在チェック
    if aws s3api head-bucket --bucket "$bucket_name" 2>/dev/null; then
        log_info "S3バケット '$bucket_name' は既に存在します"
    else
        log_info "S3バケット '$bucket_name' を作成しています..."
        aws s3api create-bucket \
            --bucket "$bucket_name" \
            --region "$region" \
            --create-bucket-configuration LocationConstraint="$region"
        
        # バージョニング有効化
        aws s3api put-bucket-versioning \
            --bucket "$bucket_name" \
            --versioning-configuration Status=Enabled
        
        # パブリックアクセスブロック
        aws s3api put-public-access-block \
            --bucket "$bucket_name" \
            --public-access-block-configuration \
            "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
    fi
}

# 基盤インフラ構築
deploy_base_infrastructure() {
    log_info "基盤インフラを構築しています..."
    
    cd terraform/base-infrastructure
    
    terraform init
    terraform plan
    terraform apply -auto-approve
    
    cd -
    
    log_info "基盤インフラの構築が完了しました！"
}

# メイン処理
main() {
    log_info "=== 基盤インフラセットアップ開始 ==="
    
    # Terraformバックエンドセットアップ
    setup_terraform_backend
    
    # 基盤インフラ構築
    deploy_base_infrastructure
    
    log_info "=== セットアップ完了 ==="
    log_info "新しいアプリを作成するには: ./scripts/create-new-app.sh <app_name>"
}

main "$@"