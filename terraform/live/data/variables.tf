variable "environment" {
  description = "dev | stage | prod."
  type        = string

  validation {
    condition     = contains(["dev", "stage", "prod"], var.environment)
    error_message = "environment must be dev, stage, or prod."
  }
}

variable "region" {
  description = "Region for this environment's data plane."
  type        = string
  default     = "us-west-2"
}

variable "account_role_arn" {
  description = "Role to assume into this environment's workload account. Null = run in-account."
  type        = string
  default     = null
}

variable "vpc_cidr" {
  description = "CIDR for this environment's VPC. Keep them distinct per env for future peering."
  type        = string
  default     = "10.0.0.0/16"
}

variable "database_name" {
  description = "Initial database in the cluster. Note: 'comments' is a reserved word for aurora-postgresql, so the app's DB is 'commentsdb'."
  type        = string
  default     = "commentsdb"
}

variable "min_acu" {
  description = "Minimum Aurora Capacity Units. 0 = scale to zero when idle (cheap)."
  type        = number
  default     = 0
}

variable "max_acu" {
  description = "Maximum Aurora Capacity Units."
  type        = number
  default     = 2
}

variable "seconds_until_auto_pause" {
  description = "Idle seconds before scaling to 0 ACU (300-86400). Dev pauses fast to save cost."
  type        = number
  default     = 300
}

variable "skip_final_snapshot" {
  description = "Skip final snapshot on destroy (true for dev)."
  type        = bool
  default     = true
}

variable "deletion_protection" {
  description = "Protect the cluster from deletion (true for prod)."
  type        = bool
  default     = false
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
