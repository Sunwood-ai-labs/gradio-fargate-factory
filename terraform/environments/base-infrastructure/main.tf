module "vpc" {
  source       = "../../modules/vpc"
  project_name = var.project_name
}

module "alb" {
  source            = "../../modules/alb"
  project_name      = var.project_name
  vpc_id            = module.vpc.vpc_id
  public_subnet_ids = module.vpc.public_subnet_ids
}

module "ecs" {
  source       = "../../modules/ecs"
  project_name = var.project_name
}

module "iam" {
  source       = "../../modules/iam"
  project_name = var.project_name
  aws_region   = var.aws_region
}

output "vpc_id" {
  value = module.vpc.vpc_id
}
output "public_subnet_ids" {
  value = module.vpc.public_subnet_ids
}
output "alb_dns_name" {
  value = module.alb.alb_dns_name
}
output "ecs_cluster_name" {
  value = module.ecs.ecs_cluster_name
}