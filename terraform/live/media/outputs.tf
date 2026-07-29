output "ingest_bucket" {
  description = "Upload lesson videos here."
  value       = module.media.ingest_bucket
}

output "output_bucket" {
  description = "Transcoded outputs (private; served via CloudFront)."
  value       = module.media.output_bucket
}

output "media_url" {
  description = "Custom media base URL. A recipe video plays from https://media.cohns.net/<video_key>/hls/…"
  value       = "https://${var.domain_name}"
}

output "media_cdn_domain" {
  description = "The underlying *.cloudfront.net domain."
  value       = module.media.media_cdn_domain
}

output "submit_lambda_name" {
  description = "The job-submit Lambda."
  value       = module.media.submit_lambda_name
}
