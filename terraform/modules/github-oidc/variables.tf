variable "github_org" {
  description = "GitHub org or user that owns the repo."
  type        = string
}

variable "github_repo" {
  description = "Repository name."
  type        = string
}

variable "github_org_id" {
  description = "Numeric GitHub org/owner id, part of the immutable OIDC subject. Public (queryable via the API); stable for the life of the org."
  type        = string
}

variable "github_repo_id" {
  description = "Numeric GitHub repository id, part of the immutable OIDC subject. Changes if the repo is deleted and recreated — which is the point."
  type        = string
}

variable "role_name" {
  description = "Name of the IAM role GitHub Actions will assume."
  type        = string
}

variable "allowed_branches" {
  description = "Branches whose workflow runs may assume this role."
  type        = list(string)
  default     = []
}

variable "allowed_environments" {
  description = "GitHub Environments whose runs may assume this role. Environments support required reviewers, which is how prod gets a manual approval gate."
  type        = list(string)
  default     = []
}

variable "allowed_tag_patterns" {
  description = "Tag patterns whose runs may assume this role, e.g. [\"v*\"]."
  type        = list(string)
  default     = []
}

variable "create_oidc_provider" {
  description = "Create the GitHub OIDC provider in this account. Set false if one already exists."
  type        = bool
  default     = true
}

variable "oidc_provider_arn" {
  description = "Existing OIDC provider ARN, used when create_oidc_provider is false."
  type        = string
  default     = null
}

variable "managed_policy_arns" {
  description = "Managed policies to attach. Prefer a scoped inline policy over AdministratorAccess."
  type        = list(string)
  default     = []
}

variable "inline_policy_json" {
  description = "Scoped inline policy for the deploy role."
  type        = string
  default     = null
}

variable "create_inline_policy" {
  description = "Whether to attach the inline policy. A static flag, so the resource count never depends on inline_policy_json — which is often an apply-time value (it references ARNs of resources created in the same run)."
  type        = bool
  default     = false
}

variable "max_session_duration" {
  description = "Max session length in seconds. Keep it just longer than the slowest pipeline."
  type        = number
  default     = 3600
}

variable "tags" {
  description = "Tags applied to every resource in this module."
  type        = map(string)
  default     = {}
}
