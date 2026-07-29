variable "region" {
  description = "Region for the photo library."
  type        = string
  default     = "us-west-2"
}

variable "account_role_arn" {
  description = "Role to assume into the account hosting the library (prod). Null = run in-account. Set in family.auto.tfvars."
  type        = string
  default     = null
}

variable "name" {
  description = "Name prefix for the library's resources."
  type        = string
  default     = "cohns-family"
}

variable "cors_origins" {
  description = "Site origins allowed to call the library API and receive presigned URLs."
  type        = list(string)
  default = [
    "https://www.cohns.net",
    "https://steve.cohns.net",
    "https://dev.cohns.net",
    "http://localhost:5173",
  ]
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
