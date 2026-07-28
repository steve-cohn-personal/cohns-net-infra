variable "environment" {
  description = "dev | stage | prod."
  type        = string

  validation {
    condition     = contains(["dev", "stage", "prod"], var.environment)
    error_message = "environment must be dev, stage, or prod."
  }
}

variable "region" {
  description = "Region for this environment's compute."
  type        = string
  default     = "us-west-2"
}

variable "account_role_arn" {
  description = "Role to assume into this environment's workload account. Null = run in-account."
  type        = string
  default     = null
}

variable "dns_account_role_arn" {
  description = "Role to assume into the DNS-owning account (env account for dev/stage subzone, shared-services for prod apex)."
  type        = string
  default     = null
}

variable "hosted_zone_id" {
  description = "Route53 zone id for the API record (the delegated subzone for dev/stage; the apex for prod)."
  type        = string
}

variable "domain_name" {
  description = "Public hostname for the API, e.g. api.dev.cohns.net."
  type        = string
}

variable "container_image" {
  description = "Full comments-api image reference, e.g. <ecr>/cohns/comments-api:<tag>."
  type        = string
}

variable "desired_count" {
  description = "Number of Fargate tasks."
  type        = number
  default     = 1
}

variable "cpu_architecture" {
  description = "X86_64 or ARM64."
  type        = string
  default     = "X86_64"
}

variable "auto_create_tables" {
  description = "Have the app create tables on boot. True for dev; prod runs Alembic as a migration step instead."
  type        = bool
  default     = true
}

variable "jwks_url" {
  description = "Cognito user-pool JWKS URL for RS256 verification. Empty until Cognito exists (Phase 3)."
  type        = string
  default     = ""
}

variable "cors_origins" {
  description = "Allowed CORS origins for the API."
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
