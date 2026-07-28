variable "region" {
  description = "Region for the media pipeline."
  type        = string
  default     = "us-west-2"
}

variable "account_role_arn" {
  description = "Role to assume into the account hosting media (prod). Null = run in-account."
  type        = string
  default     = null
}

variable "name" {
  description = "Name prefix for the pipeline's resources."
  type        = string
  default     = "cohns-media"
}

variable "cors_origins" {
  description = "Origins allowed to fetch media for cross-origin HLS playback."
  type        = list(string)
  default     = ["https://www.cohns.net", "https://steve.cohns.net"]
}

variable "github_org" {
  description = "GitHub org, for the Repo tag."
  type        = string
  default     = "steve-cohn-personal"
}

variable "github_repo" {
  description = "GitHub repo, for the Repo tag."
  type        = string
  default     = "cohns-net-infra"
}
