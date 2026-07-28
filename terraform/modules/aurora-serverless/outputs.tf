output "cluster_endpoint" {
  description = "Writer endpoint (host) for the cluster."
  value       = aws_rds_cluster.this.endpoint
}

output "reader_endpoint" {
  description = "Reader endpoint for the cluster."
  value       = aws_rds_cluster.this.reader_endpoint
}

output "port" {
  description = "Postgres port."
  value       = aws_rds_cluster.this.port
}

output "database_name" {
  description = "The initial database name."
  value       = aws_rds_cluster.this.database_name
}

output "master_user_secret_arn" {
  description = "Secrets Manager ARN holding the generated master credentials. The app reads this — no password in state."
  value       = aws_rds_cluster.this.master_user_secret[0].secret_arn
}

output "security_group_id" {
  description = "The cluster security group; grant the app egress to this."
  value       = aws_security_group.this.id
}

output "cluster_arn" {
  description = "The cluster ARN."
  value       = aws_rds_cluster.this.arn
}

output "read_secret_policy_arn" {
  description = "IAM policy granting GetSecretValue on the DB secret. Attach to the app's task/pod role."
  value       = aws_iam_policy.read_secret.arn
}
