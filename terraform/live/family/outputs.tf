output "bucket_name" {
  description = "The private photo bucket. Upload library/<id>.jpg + library/thumb/<id>.jpg + manifest.json."
  value       = module.library.bucket_name
}

output "api_endpoint" {
  description = "Base URL of the library API."
  value       = module.library.api_endpoint
}

output "photos_url" {
  description = "The /photos URL the site fetches (with a Cognito ID token)."
  value       = module.library.photos_url
}

output "list_lambda_name" {
  description = "The list Lambda function name."
  value       = module.library.list_lambda_name
}
