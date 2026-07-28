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
