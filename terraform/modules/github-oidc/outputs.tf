output "role_arn" {
  description = "ARN of the deploy role. This is the only value GitHub Actions needs — and it is not a secret."
  value       = aws_iam_role.deploy.arn
}

output "role_name" {
  description = "Name of the deploy role."
  value       = aws_iam_role.deploy.name
}

output "oidc_provider_arn" {
  description = "ARN of the GitHub OIDC provider in this account."
  value       = local.provider_arn
}
