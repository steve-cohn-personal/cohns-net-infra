output "grafana_folder_url" {
  description = "The cohns.net dashboard folder in the Grafana stack."
  value       = "${var.grafana_url}/dashboards/f/${grafana_folder.cohns.uid}"
}

output "slo_dashboard_url" {
  description = "The SLO dashboard (authenticated view)."
  value       = "${var.grafana_url}/d/${grafana_dashboard.slo.uid}"
}

output "slo_public_url" {
  description = "The public SLO dashboard — linked from cohns.net/observability."
  value       = "${var.grafana_url}/public-dashboards/${grafana_dashboard_public.slo.access_token}"
}

output "aurora_cost_public_url" {
  description = "The public Aurora scale-to-zero cost dashboard — linked from cohns.net/observability. Null until enable_cloudwatch is true."
  value       = var.enable_cloudwatch ? "${var.grafana_url}/public-dashboards/${grafana_dashboard_public.aurora_cost[0].access_token}" : null
}

output "cloudwatch_reader_role_arn" {
  description = "The role Grafana Cloud assumes to read this account's CloudWatch. Null until enable_cloudwatch is true."
  value       = var.enable_cloudwatch ? aws_iam_role.grafana_cloudwatch[0].arn : null
}

output "alarms_topic_arn" {
  description = "SNS topic that fans out infrastructure alarms."
  value       = aws_sns_topic.alarms.arn
}
