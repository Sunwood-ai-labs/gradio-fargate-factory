output "ecr_repository_url" {
  description = "ECRリポジトリURL"
  value       = aws_ecr_repository.app.repository_url
}

output "ecs_service_name" {
  description = "ECSサービス名"
  value       = aws_ecs_service.app.name
}

output "target_group_arn" {
  description = "ターゲットグループARN"
  value       = aws_lb_target_group.app.arn
}

output "cloudwatch_log_group" {
  description = "CloudWatchログググループ名"
  value       = aws_cloudwatch_log_group.app.name
}

output "app_url_path" {
  description = "アプリアクセスパス"
  value       = var.app_path
}