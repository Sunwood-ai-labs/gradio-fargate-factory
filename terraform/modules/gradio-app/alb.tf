# ALBリスナールール（パスベースルーティング）
resource "aws_lb_listener_rule" "app" {
  listener_arn = var.alb_listener_arn
  priority     = var.priority

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }

  condition {
    path_pattern {
      values = [var.app_path]
    }
  }

  tags = {
    Name        = "${var.app_name}-rule"
    Project     = var.project_name
    Environment = var.environment
  }
}