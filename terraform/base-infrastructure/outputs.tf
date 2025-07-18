output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

output "private_subnet_ids" {
  description = "プライベートサブネットIDs"
  value       = aws_subnet.private[*].id
}

output "public_subnet_ids" {
  description = "パブリックサブネットIDs"
  value       = aws_subnet.public[*].id
}

output "ecs_cluster_name" {
  description = "ECSクラスター名"
  value       = aws_ecs_cluster.main.name
}

output "ecs_cluster_id" {
  description = "ECSクラスターID"
  value       = aws_ecs_cluster.main.id
}

output "alb_arn" {
  description = "ALB ARN"
  value       = aws_lb.main.arn
}

output "alb_dns_name" {
  description = "ALB DNS名"
  value       = aws_lb.main.dns_name
}

output "alb_zone_id" {
  description = "ALB Zone ID"
  value       = aws_lb.main.zone_id
}

output "alb_listener_arn" {
  description = "ALBリスナーARN"
  value       = aws_lb_listener.main.arn
}

output "alb_security_group_id" {
  description = "ALBセキュリティグループID"
  value       = aws_security_group.alb.id
}

output "ecs_security_group_id" {
  description = "ECSタスク用セキュリティグループID"
  value       = module.alb.ecs_tasks_security_group_id
}
output "ecs_security_group_id" {
  description = "ECSタスク用セキュリティグループID"
  value       = module.alb.ecs_tasks_security_group_id
}

output "ecs_task_execution_role_arn" {
  description = "ECSタスク実行ロールARN"
  value       = aws_iam_role.ecs_task_execution_role.arn
}

output "ecs_task_role_arn" {
  description = "ECSタスクロールARN"
  value       = aws_iam_role.ecs_task_role.arn
}