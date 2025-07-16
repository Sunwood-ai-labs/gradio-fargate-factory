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
    key    = "gradio-ecs/apps/image-filter/terraform.tfstate"
    region = "ap-northeast-1"
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      App         = "image-filter"
      ManagedBy   = "Terraform"
    }
  }
}

data "terraform_remote_state" "base" {
  backend = "s3"
  config = {
    bucket = "your-terraform-state-bucket"
    key    = "gradio-ecs/base-infrastructure/terraform.tfstate"
    region = "ap-northeast-1"
  }
}

module "gradio_app" {
  source = "../../../terraform/modules/gradio-app"

  app_name     = "image-filter"
  app_path     = "/image-filter/*"
  app_port     = 7860
  priority     = 101

  project_name = var.project_name
  environment  = var.environment
  aws_region   = var.aws_region

  vpc_id                       = data.terraform_remote_state.base.outputs.vpc_id
  private_subnet_ids           = data.terraform_remote_state.base.outputs.private_subnet_ids
  ecs_cluster_id               = data.terraform_remote_state.base.outputs.ecs_cluster_id
  alb_listener_arn             = data.terraform_remote_state.base.outputs.alb_listener_arn
  ecs_security_group_id        = data.terraform_remote_state.base.outputs.ecs_security_group_id
  ecs_task_execution_role_arn  = data.terraform_remote_state.base.outputs.ecs_task_execution_role_arn
  ecs_task_role_arn            = data.terraform_remote_state.base.outputs.ecs_task_role_arn
}