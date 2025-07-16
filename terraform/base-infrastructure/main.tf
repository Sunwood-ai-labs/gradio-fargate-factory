terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  
  backend "s3" {
    # 事前にS3バケットを作成してください
    bucket = "sunwood-ai-labs-gff-state"
    key    = "gradio-ecs/base-infrastructure/terraform.tfstate"
    region = "ap-northeast-1"
  }
}

provider "aws" {
  region = var.aws_region
  
  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "Terraform"
      Component   = "BaseInfrastructure"
    }
  }
}
module "myapp" {
  source        = "../modules/gradio-app"
  app_name      = "myapp"
  app_path      = "/myapp/*"
  app_port      = 7860
  project_name  = "gradio-fargate-factory"
  # 必要に応じてVPCやALB等のIDも渡す
  # vpc_id     = module.vpc.vpc_id
  # alb_arn    = module.alb.alb_arn
  # など
}