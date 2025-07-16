variable "app_name" {
  description = "アプリケーション名"
  type        = string
}

variable "app_path" {
  description = "ALBパスパターン（例: /myapp/*）"
  type        = string
}

variable "app_port" {
  description = "アプリケーションポート"
  type        = number
  default     = 7860
}

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

# 基盤インフラからの参照値
variable "vpc_id" {
  description = "VPC ID"
  type        = string
}

variable "private_subnet_ids" {
  description = "プライベートサブネットIDs"
  type        = list(string)
}

variable "ecs_cluster_id" {
  description = "ECSクラスターID"
  type        = string
}

variable "alb_listener_arn" {
  description = "ALBリスナーARN"
  type        = string
}

variable "ecs_security_group_id" {
  description = "ECSタスクセキュリティグループID"
  type        = string
}

variable "ecs_task_execution_role_arn" {
  description = "ECSタスク実行ロールARN"
  type        = string
}

variable "ecs_task_role_arn" {
  description = "ECSタスクロールARN"
  type        = string
}

variable "cpu" {
  description = "CPU設定"
  type        = number
  default     = 256
}

variable "memory" {
  description = "メモリ設定"
  type        = number
  default     = 512
}

variable "desired_count" {
  description = "希望タスク数"
  type        = number
  default     = 1
}

variable "priority" {
  description = "ALBリスナールール優先度"
  type        = number
}