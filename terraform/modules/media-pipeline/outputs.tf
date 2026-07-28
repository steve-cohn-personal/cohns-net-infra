output "ingest_bucket" {
  description = "Upload source videos here; an ObjectCreated event kicks off transcoding."
  value       = aws_s3_bucket.ingest.id
}

output "output_bucket" {
  description = "Transcoded HLS/MP4/thumbnail outputs land here (private; served via CloudFront)."
  value       = aws_s3_bucket.output.id
}

output "media_cdn_domain" {
  description = "CloudFront domain serving the transcoded media. Build recipe video URLs from this + <video_key>/hls/…"
  value       = aws_cloudfront_distribution.media.domain_name
}

output "mediaconvert_role_arn" {
  description = "The role MediaConvert assumes for jobs."
  value       = aws_iam_role.mediaconvert.arn
}

output "submit_lambda_name" {
  description = "The job-submit Lambda."
  value       = aws_lambda_function.submit.function_name
}
