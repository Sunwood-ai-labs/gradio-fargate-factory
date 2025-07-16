# Gradio Fargate Factory

## 🚀 AWS ECS Fargate Gradio動的デプロイシステム

複数のGradioアプリをAWS ECS Fargateにパスベースルーティングで動的にデプロイできるシステムです。

## ✨ 特徴

- **動的アプリ追加**: 新しいGradioアプリを簡単に追加・デプロイ
- **パスベースルーティング**: 1つのALBで複数アプリを管理
- **独立デプロイ**: 各アプリは独立してデプロイ・更新可能
- **自動化**: スクリプトによる完全自動化
- **スケーラブル**: サーバーレスで自動スケーリング

## 🏗️ システム構成

```
ALB (Load Balancer)
├── /app1/* → Gradio App 1 (ECS Fargate)
├── /app2/* → Gradio App 2 (ECS Fargate)
├── /app3/* → Gradio App 3 (ECS Fargate)
└── /       → 404 (デフォルト)
```

## 📋 前提条件

- AWS CLI設定済み
- Terraform >= 1.0インストール済み
- Docker インストール済み
- 適切なAWS権限（ECS、ALB、ECR、VPC、IAM等）

## 🚀 セットアップ手順

### 1. リポジトリクローン・初期設定

```bash
git clone <このリポジトリ>
cd gradio-ecs-deployment

# 実行権限付与
chmod +x scripts/*.sh
```

### 2. S3バケット名設定

以下のファイルでS3バケット名を変更してください：

```bash
# terraform/base-infrastructure/main.tf
# terraform/modules/gradio-app/main.tf の例
# scripts/create-new-app.sh
# scripts/setup-infrastructure.sh

# "your-terraform-state-bucket" を適切な名前に変更
```

### 3. 基盤インフラ構築（一度だけ）

```bash
./scripts/setup-infrastructure.sh
```

これにより以下が作成されます：
- VPC・サブネット・NATゲートウェイ
- ECSクラスター
- ALB（ロードバランサー）
- IAMロール
- セキュリティグループ

## 📱 アプリ運用

### 新しいアプリ作成

```bash
# 基本的な作成
./scripts/create-new-app.sh my-chatbot

# カスタムパスとポート指定
./scripts/create-new-app.sh image-classifier /classifier/* 8080
```

### アプリ開発

```bash
cd apps/my-chatbot/src

# app.pyを編集してGradioアプリを実装
nano app.py

# 必要に応じてrequirements.txtも更新
nano requirements.txt
```

### アプリデプロイ

```bash
cd apps/my-chatbot
./deploy.sh
```

デプロイ処理：
1. Terraformでインフラ作成（ECR、ECSサービス、ALBルーティング）
2. Dockerイメージビルド
3. ECRにプッシュ
4. ECSサービス更新

### アプリ更新

アプリコードを変更した後：

```bash
cd apps/my-chatbot
./deploy.sh  # 同じコマンドで更新
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
# apps/my-app/terraform/main.tf
module "gradio_app" {
  source = "../../terraform/modules/gradio-app"
  
  # ...他の設定...
  
  cpu           = 512   # デフォルト: 256
  memory        = 1024  # デフォルト: 512
  desired_count = 2     # デフォルト: 1
}
```

### 環境変数追加

```hcl
# terraform/modules/gradio-app/main.tf のcontainer_definitionsで
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