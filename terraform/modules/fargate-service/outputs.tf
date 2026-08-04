output "alb_dns_name" {
  description = "The ALB's DNS name — point a Route53 alias at this."
  value       = aws_lb.this.dns_name
}

output "alb_zone_id" {
  description = "The ALB's hosted zone id, for a Route53 alias record."
  value       = aws_lb.this.zone_id
}

output "alb_arn" {
  description = "The ALB ARN."
  value       = aws_lb.this.arn
}

output "cluster_name" {
  description = "The ECS cluster name."
  value       = aws_ecs_cluster.this.name
}

output "service_name" {
  description = "The ECS service name."
  value       = aws_ecs_service.this.name
}

output "task_role_arn" {
  description = "The task role ARN (the app's identity)."
  value       = aws_iam_role.task.arn
}

output "task_role_name" {
  description = "The task role name — attach extra policies to the app's identity."
  value       = aws_iam_role.task.name
}
