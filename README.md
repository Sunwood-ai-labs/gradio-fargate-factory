<p align="center">
  <img src="header.png" alt="Gradio Fargate Factory" width="600"/>
</p>

<h1 align="center">Gradio Fargate Factory</h1>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9+-blue?logo=python">
  <img src="https://img.shields.io/badge/FastAPI-API-green?logo=fastapi">
  <img src="https://img.shields.io/badge/AWS-ECS%20Fargate-orange?logo=amazon-aws">
  <img src="https://img.shields.io/badge/Terraform-IaC-purple?logo=terraform">
  <img src="https://img.shields.io/badge/Docker-Container-blue?logo=docker">
</p>

## 🚀 AWS ECS Fargate Gradio動的デプロイシステム

GitリポジトリからGradioアプリをAWS ECS Fargateに**APIベースで動的にデプロイ**できるシステムです。

## ✨ 特徴

- **APIベース動的デプロイ**: FastAPIサーバーによる自動デプロイ
- **Gitリポジトリ統合**: GitリポジトリURLを指定するだけで自動デプロイ
- **パスベースルーティング**: 1つのALBで複数アプリを管理
- **完全自動化**: Docker build、ECRプッシュ、ECSサービス作成まで自動
- **スケーラブル**: Fargateによる自動スケーリング

## 🏗️ システム構成

```
┌─────────────────────────────────────────────────────────────┐
│                    Deploy Server (FastAPI)                  │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ API: /deploy                                            │  │
│  │  ├─ Git clone from repository                           │  │
│  │  ├─ Docker build & push to ECR                         │  │
│  │  ├─ Create/update ECS service                           │  │
│  │  └─ Configure ALB routing                               │  │
│  └─────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────┐
│                      AWS Infrastructure                      │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ ALB (Load Balancer)                                     │  │
│  │ ├── /app1/* → Gradio App 1 (ECS Fargate)              │  │
│  │ ├── /app2/* → Gradio App 2 (ECS Fargate)              │  │
│  │ ├── /app3/* → Gradio App 3 (ECS Fargate)              │  │
│  │ └── /       → 404 (デフォルト)                          │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                             │
│  ECS Cluster | ECR Registry | VPC | IAM Roles             │
└─────────────────────────────────────────────────────────────┘
```

## 📋 前提条件

- AWS CLI設定済み
- Terraform >= 1.0インストール済み
- Docker インストール済み
- Python 3.9+ インストール済み
- 適切なAWS権限（ECS、ALB、ECR、VPC、IAM等）

## 🚀 セットアップ手順

### 1. リポジトリクローン・初期設定

```bash
git clone https://github.com/Sunwood-ai-labs/gradio-fargate-factory.git
cd gradio-fargate-factory

# 実行権限付与
chmod +x scripts/*.sh
```

### 2. Terraform S3バケット設定

`terraform/base-infrastructure/main.tf`でS3バケット名を変更：

```hcl
backend "s3" {
  bucket = "your-terraform-state-bucket"  # 適切な名前に変更
  key    = "gradio-ecs/base-infrastructure/terraform.tfstate"
  region = "ap-northeast-1"
}
```

### 3. 基盤インフラ構築（一度だけ）

```bash
cd terraform/base-infrastructure
terraform init
terraform plan
terraform apply
```

これにより以下が作成されます：
- VPC・サブネット・NATゲートウェイ
- ECSクラスター
- ALB（ロードバランサー）
- IAMロール
- セキュリティグループ

### 4. Deploy Server設定

基盤インフラ構築後、Terraformのoutputを使って`.env`ファイルを設定：

```bash
cd ../..
cd deploy_server

# Terraformのoutputから.envファイルを設定
cp .env.example .env
```

`.env`ファイルに以下の値を設定：

```bash
# Terraformのoutputから取得
cd ../terraform/base-infrastructure
terraform output

# 以下を.envファイルに設定
ALB_ARN=<terraform output alb_arn>
ALB_DNS_NAME=<terraform output alb_dns_name>
ALB_LISTENER_ARN=<terraform output alb_listener_arn>
ALB_SECURITY_GROUP_ID=<terraform output alb_security_group_id>
ALB_ZONE_ID=<terraform output alb_zone_id>
ECS_CLUSTER_ID=<terraform output ecs_cluster_id>
ECS_CLUSTER_NAME=<terraform output ecs_cluster_name>
ECS_SECURITY_GROUP_ID=<terraform output ecs_security_group_id>
ECS_TASK_EXECUTION_ROLE_ARN=<terraform output ecs_task_execution_role_arn>
ECS_TASK_ROLE_ARN=<terraform output ecs_task_role_arn>
PRIVATE_SUBNET_IDS=<terraform output private_subnet_ids>
PUBLIC_SUBNET_IDS=<terraform output public_subnet_ids>
VPC_ID=<terraform output vpc_id>
```

### 5. Deploy Server起動

```bash
cd deploy_server

# 依存関係インストール
pip install -r pyproject.toml

# サーバー起動
python main.py
```

Deploy Serverが `http://localhost:8000` で起動します。

## 📱 アプリ運用

### Deploy Server APIでのデプロイ

Deploy Serverが起動したら、APIを使ってGradioアプリをデプロイできます。

#### 1. APIエンドポイント

```
POST http://localhost:8000/deploy
```

#### 2. リクエストパラメータ

```json
{
  "app_name": "myapp",              // アプリ名（必須）
  "alb_path": "/myapp/*",           // ALBパスパターン（必須）
  "git_repo_url": "https://github.com/user/repo.git",  // GitリポジトリURL（オプション）
  "docker_context": "./",           // Dockerfileがあるディレクトリ（デフォルト: ./）
  "dockerfile": "Dockerfile",       // Dockerファイル名（デフォルト: Dockerfile）
  "cpu": "2048",                    // CPU（デフォルト: 2048）
  "memory": "4096",                 // メモリ（デフォルト: 4096）
  "force_recreate": false           // 強制再作成フラグ（デフォルト: false）
}
```

#### 3. デプロイクライアント使用例

`deploy_client.py`を使った便利なデプロイ：

```bash
cd deploy_server

# 基本的なデプロイ
python deploy_client.py \
  --app myapp \
  --path "/myapp/*" \
  --git "https://github.com/user/gradio-app.git"

# リソースを指定してデプロイ
python deploy_client.py \
  --app image-classifier \
  --path "/classifier/*" \
  --git "https://github.com/user/image-classifier.git" \
  --cpu 4096 \
  --mem 8192

# 強制再作成
python deploy_client.py \
  --app myapp \
  --path "/myapp/*" \
  --git "https://github.com/user/gradio-app.git" \
  --force
```

#### 4. 自動デプロイ処理

APIコールすると以下が自動実行されます：

1. **Gitクローン**: 指定リポジトリを一時ディレクトリにクローン
2. **Dockerビルド**: Dockerfile（またはデフォルトDockerfile）でイメージビルド
3. **ECRプッシュ**: ビルドしたイメージをECRにプッシュ
4. **ECSサービス作成/更新**: Fargateサービスを作成または更新
5. **ALBルーティング設定**: 指定パスパターンでルーティング設定
6. **ヘルスチェック設定**: Gradioアプリのヘルスチェック設定

### アプリ更新

同じAPIコールで更新が可能：

```bash
# 同じコマンドで更新
python deploy_client.py \
  --app myapp \
  --path "/myapp/*" \
  --git "https://github.com/user/gradio-app.git"
```

### 実際の使用例

`sample_client.py`での実際のデプロイ例：

```python
import requests
import json

API_URL = "http://localhost:8000/deploy"

payload = {
    "app_name": "myapp",
    "alb_path": "/myapp/*",
    "git_repo_url": "http://192.168.0.131:3000/Sunwood-ai-labs/gradio-ff-demo-001.git",
    "cpu": "4096",
    "memory": "8192"
}

response = requests.post(API_URL, json=payload)
print(response.json())
```

レスポンス例：
```json
{
  "status": "success",
  "message": "myapp deployed successfully!",
  "deployed_url": "http://gradio-ecs-alb-xxx.ap-northeast-1.elb.amazonaws.com/myapp",
  "app_name": "myapp",
  "cpu": "4096",
  "memory": "8192",
  "deployment_type": "create",
  "estimated_ready_time": "5-10 minutes"
}
```

## 🔧 運用コマンド

### ログ確認

```bash
# リアルタイムログ
aws logs tail /ecs/my-chatbot --follow --region ap-northeast-1

# 過去のログ
aws logs tail /ecs/my-chatbot --since 1h --region ap-northeast-1
```

### サービス状態確認

```bash
# ECSサービス状態
aws ecs describe-services \
  --cluster gradio-ecs-cluster \
  --services my-chatbot \
  --region ap-northeast-1

# タスク一覧
aws ecs list-tasks \
  --cluster gradio-ecs-cluster \
  --service-name my-chatbot \
  --region ap-northeast-1
```

### デバッグ（ECS Exec）

```bash
# コンテナ内にアクセス
aws ecs execute-command \
  --cluster gradio-ecs-cluster \
  --task <task-id> \
  --container my-chatbot \
  --interactive \
  --command "/bin/bash" \
  --region ap-northeast-1
```

## 📊 アプリ例

### シンプルなテキスト処理アプリ

```python
# apps/text-processor/src/app.py
import gradio as gr

def process_text(text, operation):
    if operation == "uppercase":
        return text.upper()
    elif operation == "lowercase":
        return text.lower()
    elif operation == "reverse":
        return text[::-1]
    return text

interface = gr.Interface(
    fn=process_text,
    inputs=[
        gr.Textbox(label="入力テキスト"),
        gr.Dropdown(["uppercase", "lowercase", "reverse"], label="操作")
    ],
    outputs=gr.Textbox(label="結果"),
    title="テキスト処理アプリ"
)

interface.launch(server_name="0.0.0.0", server_port=7860)
```

### 画像処理アプリ

```python
# apps/image-filter/src/app.py
import gradio as gr
from PIL import Image, ImageFilter

def apply_filter(image, filter_type):
    if filter_type == "blur":
        return image.filter(ImageFilter.BLUR)
    elif filter_type == "sharpen":
        return image.filter(ImageFilter.SHARPEN)
    elif filter_type == "edge":
        return image.filter(ImageFilter.FIND_EDGES)
    return image

interface = gr.Interface(
    fn=apply_filter,
    inputs=[
        gr.Image(type="pil"),
        gr.Dropdown(["blur", "sharpen", "edge"], label="フィルター")
    ],
    outputs=gr.Image(type="pil"),
    title="画像フィルターアプリ"
)

interface.launch(server_name="0.0.0.0", server_port=7860)
```

## 🔧 カスタマイズ

### リソース設定変更

アプリのCPU・メモリを変更：

```hcl
```

### 環境変数追加

```hcl
environment = [
  {
    name  = "PORT"
    value = tostring(var.app_port)
  },
  {
    name  = "APP_NAME"
    value = var.app_name
  },
  {
    name  = "CUSTOM_VAR"
    value = "custom_value"
  }
]
```

## 🛠️ トラブルシューティング

### よくある問題

1. **ECRログインエラー**
   ```bash
   aws configure list  # AWS認証情報確認
   aws ecr get-login-password --region ap-northeast-1  # 手動ログインテスト
   ```

2. **Terraformエラー**
   ```bash
   terraform init -reconfigure  # バックエンド再初期化
   ```

3. **コンテナ起動エラー**
   ```bash
   # ローカルでDockerイメージテスト
   cd apps/my-app/src
   docker build -t test .
   docker run -p 7860:7860 test
   ```

4. **ALBヘルスチェック失敗**
   - Gradioアプリがポート7860で起動しているか確認
   - ヘルスチェックパス（/）でレスポンス200が返るか確認

### リソース削除

```bash
# 特定アプリ削除
cd apps/my-app/terraform
terraform destroy

# 基盤インフラ削除（全削除）
cd terraform/base-infrastructure
terraform destroy
```

## 💰 コスト最適化

- **Fargate Spot**: 本番以外でコスト削減
- **スケジュール停止**: 開発環境で夜間停止
- **ログ保持期間**: CloudWatchログの保持期間を調整

## 🔒 セキュリティ

- **HTTPS化**: ALBでSSL証明書設定
- **認証**: Gradioアプリレベルでの認証実装
- **ネットワーク制限**: セキュリティグループでIP制限

## 📈 監視

- **CloudWatch**: メトリクス・アラーム設定
- **Container Insights**: ECS詳細監視
- **ALBアクセスログ**: S3でアクセスログ保存

---

これで動的にGradioアプリを追加・管理できるシステムの完成です！🎉