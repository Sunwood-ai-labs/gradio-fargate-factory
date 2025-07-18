variable "project_name" {
  description = "プロジェクト名"
  type        = string
}

variable "vpc_id" {
  description = "VPCのID"
  type        = string
}

variable "public_subnet_ids" {
  description = "パブリックサブネットのIDリスト"
  type        = list(string)
}