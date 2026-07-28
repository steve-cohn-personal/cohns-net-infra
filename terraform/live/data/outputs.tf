output "vpc_id" {
  description = "The environment VPC."
  value       = module.network.vpc_id
}

output "db_endpoint" {
  description = "Aurora writer endpoint. The comments service connects here."
  value       = module.db.cluster_endpoint
}

output "db_reader_endpoint" {
  description = "Aurora reader endpoint."
  value       = module.db.reader_endpoint
}

output "db_name" {
  description = "Initial database name."
  value       = module.db.database_name
}

output "db_secret_arn" {
  description = "Secrets Manager ARN with the generated master credentials — grant the app read on this, not a password."
  value       = module.db.master_user_secret_arn
}

output "db_security_group_id" {
  description = "The cluster security group id."
  value       = module.db.security_group_id
}

output "db_read_secret_policy_arn" {
  description = "Attach to the comments-api task/pod role so it can read its DB credentials."
  value       = module.db.read_secret_policy_arn
}
