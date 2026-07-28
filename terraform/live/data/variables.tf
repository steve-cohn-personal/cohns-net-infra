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
  description = "Initial database in the cluster."
  type        = string
  default     = "comments"
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
