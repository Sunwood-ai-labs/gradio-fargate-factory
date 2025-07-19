output "vpc_id" {
  value = var.vpc_id
}

output "public_subnet_ids" {
  value = var.public_subnet_ids
}

output "private_subnet_ids" {
  value = var.private_subnet_ids
}

output "alb_dns_name" {
  value = module.alb.alb_dns_name
}

output "ecs_cluster_name" {
  value = module.ecs.ecs_cluster_name
}

output "ecs_cluster_id" {
  value = module.ecs.ecs_cluster_id
}

output "alb_arn" {
  value = module.alb.alb_arn
}

output "alb_zone_id" {
  value = module.alb.alb_zone_id
}

output "alb_listener_arn" {
  value = module.alb.alb_listener_arn
}

output "alb_security_group_id" {
  value = module.alb.alb_security_group_id
}

output "ecs_task_execution_role_arn" {
  value = module.iam.ecs_task_execution_role_arn
}

output "ecs_task_role_arn" {
  value = module.iam.ecs_task_role_arn
}

output "ecs_security_group_id" {
  description = "ECSタスク用セキュリティグループID"
  value       = module.alb.ecs_tasks_security_group_id
}

output "security_groups" {
  description = "SECURITY_GROUPS互換"
  value       = module.alb.ecs_tasks_security_group_id
}