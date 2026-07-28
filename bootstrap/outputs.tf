output "state_bucket" {
  description = "Name of the Terraform state bucket. Paste this into the backend block of every other root module."
  value       = aws_s3_bucket.state.id
}

output "state_bucket_arn" {
  description = "ARN of the state bucket, for CI deploy-role policies."
  value       = aws_s3_bucket.state.arn
}

output "region" {
  description = "Region the state bucket lives in."
  value       = var.region
}
