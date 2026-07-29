variable "name" {
  description = "Name prefix for the pipeline's resources."
  type        = string
  default     = "cohns-media"
}

variable "cors_origins" {
  description = "Origins allowed to fetch media (the site) — needed for cross-origin HLS playback."
  type        = list(string)
  default     = ["https://www.cohns.net", "https://steve.cohns.net"]
}

variable "domain_name" {
  description = "Custom domain for the media CDN (e.g. media.cohns.net). Null keeps the default *.cloudfront.net domain."
  type        = string
  default     = null
}

variable "certificate_arn" {
  description = "ACM certificate (us-east-1) for domain_name. Required when domain_name is set."
  type        = string
  default     = null
}

variable "lambda_log_retention_days" {
  description = "CloudWatch Logs retention for the job-submit Lambda."
  type        = number
  default     = 14
}

variable "tags" {
  description = "Tags applied to every resource."
  type        = map(string)
  default     = {}
}
