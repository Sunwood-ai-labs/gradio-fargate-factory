# deploy_server

GradioアプリをAWS ECS/Fargate + ECR + ALBに自動デプロイするFastAPIサーバーです。  
Terraformのoutputや.env設定を活用し、ECSサービスの作成・更新・ALBルール追加・ECRビルド/プッシュ等を一括で行います。

---

## 📁 ディレクトリ構成

```
deploy_server/
├── models/
│   ├── __init__.py
│   └── deploy.py
├── utils/
│   ├── __init__.py
│   ├── aws.py
│   └── common.py
├── .env
├── .env.example
├── .SourceSageignore
├── main.py
├── pyproject.toml
└── uv.lock
```

---

## 📝 主なファイル

- `main.py`  
  FastAPI本体。`/deploy`・`/config`エンドポイントを提供。ECR/ECS/ALB連携の中心。
- `models/deploy.py`  
  デプロイAPIのリクエストモデル定義（Pydantic）。
- `utils/common.py`  
  .envやTerraform outputのロード、設定値取得、セキュリティグループ自動設定など共通処理。
- `utils/aws.py`  
  ECSタスク定義・サービス作成/更新/削除のラッパー。
- `.env` / `.env.example`  
  AWSやTerraform、クローン先ディレクトリ等の設定例。
- `pyproject.toml`  
  依存パッケージ・プロジェクト定義。

---

## ⚙️ 必要な環境・依存

- Python 3.9 以上
- AWSアカウント（ECR/ECS/ALB利用権限）
- Terraformで事前にVPC/ALB/ECS等の基盤構築済み
- Docker（ECRへのpushに利用）
- 必要パッケージ:  
  - fastapi, pydantic, boto3, python-dotenv, uvicorn, requests, loguru, uv

インストール例:
```sh
cd deploy_server
pip install -r <(poetry export --format=requirements.txt)  # またはpyproject.toml参照
```

---

## 🛠️ .env 設定例

`.env.example` をコピーして `.env` を作成し、必要に応じて値を修正してください。

```env
AWS_REGION=ap-northeast-1
TERRAFORM_STATE_PATH=terraform/environments/base-infrastructure/terraform.tfstate
CLONE_BASE_DIR=/home/cc-company/gradio-fargate-factory/tmp
# 以下はTerraform outputで自動取得される場合は不要
# ECS_CLUSTER_NAME=gradio-ecs-cluster
# ECS_TASK_EXECUTION_ROLE_ARN=...
# VPC_ID=...
# SUBNETS=...
# SECURITY_GROUPS=...
# ALB_ARN=...
# ALB_DNS_NAME=...
# ALB_LISTENER_ARN=...
# ALB_SECURITY_GROUP_ID=...
# ECS_SECURITY_GROUP_ID=...
```

---

## 🚀 使い方

### 1. サーバー起動

uvコマンドでサーバーを起動します（推奨）:

```sh
uv run python main.py
```

> 補足:  
> `uvicorn main:app --host 0.0.0.0 --port 8002` でも起動可能です。

### 2. デプロイクライアントの実行例

`example/deploy_client.py` を使ってAPI経由でデプロイを実行できます。

```sh
uv run python example/deploy_client.py --app app7 --path "/app7*" --git http://192.168.0.131:3000/Sunwood-ai-labs/gradio-ff-demo-001.git --cpu 512 --mem 1024
```

- `--app` : デプロイするアプリ名
- `--path`: ALBのルーティングパス（例: "/app7*"）
- `--git`: デプロイ対象のGitリポジトリURL
- `--cpu`: ECSタスクのCPU（例: 512, 1024, 2048 など）
- `--mem`: ECSタスクのメモリ（例: 1024, 4096 など）

### 3. APIエンドポイント

#### `/deploy` (POST)

GradioアプリをECS+ALBにデプロイします。

- リクエスト例（JSON）:
  ```json
  {
    "app_name": "my-gradio-app",
    "docker_context": "./",
    "dockerfile": "Dockerfile",
    "alb_path": "/my-app/*",
    "git_repo_url": "https://github.com/your/repo.git",
    "cpu": "2048",
    "memory": "4096",
    "force_recreate": false
  }
  ```
- 主な処理:
  - (必要なら)Gitリポジトリをクローン
  - Dockerビルド→ECRプッシュ
  - タスク定義登録
  - ターゲットグループ/ALBルール作成
  - ECSサービス作成または更新
  - デプロイURL返却

#### `/config` (GET)

現在の設定・Terraform outputの確認。

---

## 🧩 拡張・カスタマイズ

- `utils/common.py` で設定取得やSG自動設定ロジックをカスタマイズ可能
- `utils/aws.py` でECSサービス/タスク定義の詳細を調整可能
- `.env` で各種AWSリソース名やパスを上書き可能

---

## 📝 注意・ベストプラクティス

- Terraformで基盤（VPC, ALB, ECS, IAM等）を事前に構築しておくこと
- `.env` のAWS認証情報は**絶対にコミットしない**こと
- デプロイ後、ALBのヘルスチェックやECSタスクの起動状況はAWSコンソールでも確認推奨
- デプロイ直後はサービス安定まで5-10分程度かかる場合あり

---

## 📚 参考

- [FastAPI公式](https://fastapi.tiangolo.com/)
- [AWS ECS/Fargate](https://docs.aws.amazon.com/ja_jp/AmazonECS/latest/developerguide/Welcome.html)
- [Terraform](https://www.terraform.io/)
- [Gradio](https://www.gradio.app/)
