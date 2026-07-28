output "bucket_name" {
  description = "Origin bucket name. The deploy pipeline syncs to this."
  value       = aws_s3_bucket.origin.id
}

output "bucket_arn" {
  description = "Origin bucket ARN, for scoping the CI deploy role."
  value       = aws_s3_bucket.origin.arn
}

output "distribution_id" {
  description = "CloudFront distribution ID. The deploy pipeline invalidates against this."
  value       = aws_cloudfront_distribution.this.id
}

output "distribution_arn" {
  description = "CloudFront distribution ARN, for scoping the CI deploy role."
  value       = aws_cloudfront_distribution.this.arn
}

output "distribution_domain_name" {
  description = "The *.cloudfront.net name, useful for testing before DNS propagates."
  value       = aws_cloudfront_distribution.this.domain_name
}

output "certificate_arn" {
  description = "ARN of the validated ACM certificate."
  value       = aws_acm_certificate_validation.this.certificate_arn
}

output "site_url" {
  description = "Canonical URL of the site."
  value       = "https://${var.domain_name}"
}
