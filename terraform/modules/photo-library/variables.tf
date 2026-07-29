variable "name" {
  description = "Base name for the library's resources (bucket, Lambda, API), e.g. cohns-family."
  type        = string
}

variable "cognito_issuer" {
  description = "Cognito token issuer URL — the JWT authorizer validates iss against this."
  type        = string
}

variable "cognito_client_id" {
  description = "Cognito app client id — the token audience the JWT authorizer requires (ID tokens carry it)."
  type        = string
}

variable "family_group" {
  description = "Cognito group that grants access to the library."
  type        = string
  default     = "family"
}

variable "cors_origins" {
  description = "Site origins allowed to call the API (and receive presigned URLs)."
  type        = list(string)
}

variable "url_ttl_seconds" {
  description = "Lifetime of the presigned image URLs. Short enough to be safe, long enough to browse."
  type        = number
  default     = 7200
}

variable "lambda_log_retention_days" {
  description = "CloudWatch log retention for the list Lambda."
  type        = number
  default     = 30
}

variable "noncurrent_version_expiration_days" {
  description = "Days to keep noncurrent object versions before expiring them (the populate script syncs with --delete)."
  type        = number
  default     = 7
}

variable "tags" {
  description = "Tags applied to every resource."
  type        = map(string)
  default     = {}
}
