output "api_url" {
  description = "The public API URL."
  value       = "https://${var.domain_name}"
}

output "alb_dns_name" {
  description = "The ALB DNS name (for testing before DNS propagates)."
  value       = module.service.alb_dns_name
}

output "alb_arn_suffix" {
  description = "ALB ARN suffix — the LoadBalancer dimension for CloudWatch alarms/dashboards."
  value       = module.service.alb_arn_suffix
}

output "target_group_arn_suffix" {
  description = "Target group ARN suffix — the TargetGroup dimension for host-health metrics."
  value       = module.service.target_group_arn_suffix
}

output "cluster_name" {
  description = "ECS cluster name."
  value       = module.service.cluster_name
}

output "service_name" {
  description = "ECS service name."
  value       = module.service.service_name
}

output "task_role_arn" {
  description = "The task role — the running app's identity."
  value       = module.service.task_role_arn
}
