output "bucket_name" {
  description = "The private photo bucket. Upload library/<id>.jpg + library/thumb/<id>.jpg + manifest.json here."
  value       = aws_s3_bucket.photos.id
}

output "api_endpoint" {
  description = "Base URL of the library API. The site calls GET <endpoint>/photos with a Cognito ID token."
  value       = trimsuffix(aws_apigatewayv2_stage.default.invoke_url, "/")
}

output "photos_url" {
  description = "The full /photos URL the site fetches."
  value       = "${trimsuffix(aws_apigatewayv2_stage.default.invoke_url, "/")}/photos"
}

output "list_lambda_name" {
  description = "The list Lambda function name."
  value       = aws_lambda_function.list.function_name
}
