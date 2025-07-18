terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# 個別アプリケーションはdeploy_serverで動的に作成されるため、
# 基盤インフラ（VPC、ALB、ECS Cluster、IAMロール）のみ構築