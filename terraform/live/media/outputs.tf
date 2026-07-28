output "ingest_bucket" {
  description = "Upload lesson videos here."
  value       = module.media.ingest_bucket
}

output "output_bucket" {
  description = "Transcoded outputs (private; served via CloudFront)."
  value       = module.media.output_bucket
}

output "media_cdn_domain" {
  description = "CloudFront domain for playback. A recipe video plays from https://<this>/<video_key>/hls/…"
  value       = module.media.media_cdn_domain
}

output "submit_lambda_name" {
  description = "The job-submit Lambda."
  value       = module.media.submit_lambda_name
}
