variable "project_name" {
  description = "プロジェクト名"
  type        = string
}

variable "environment" {
  description = "環境名"
  type        = string
}

variable "aws_region" {
  description = "AWSリージョン"
  type        = string
}

variable "vpc_id" {
  description = "使用する既存VPCのID"
  type        = string
}

variable "public_subnet_ids" {
  description = "使用する既存パブリックサブネットのIDリスト"
  type        = list(string)
}

variable "private_subnet_ids" {
  description = "使用する既存プライベートサブネットのIDリスト"
  type        = list(string)
}