module "alb" {
  source            = "../../modules/alb"
  project_name      = var.project_name
  vpc_id            = var.vpc_id
  public_subnet_ids = var.public_subnet_ids
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