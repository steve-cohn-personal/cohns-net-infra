variable "environment" {
  description = "dev | stage | prod. Drives naming, tagging, and the GitHub Environment gate."
  type        = string

  validation {
    condition     = contains(["dev", "stage", "prod"], var.environment)
    error_message = "environment must be dev, stage, or prod."
  }
}

variable "region" {
  description = "Primary region for this environment."
  type        = string
  default     = "us-west-2"
}

variable "domain_name" {
  description = "Canonical domain. prod: www.cohns.net, stage: stage.cohns.net, dev: dev.cohns.net."
  type        = string
}

variable "alternate_domain_names" {
  description = "Additional names on the same distribution. prod carries steve.cohns.net."
  type        = list(string)
  default     = []
}

variable "apex_zone_id" {
  description = "The cohns.net apex hosted zone (in shared-services). prod writes its records here directly; dev/stage get an NS delegation record here pointing at their subzone."
  type        = string
}

variable "account_role_arn" {
  description = "Role to assume into this environment's workload account (its OrganizationAccountAccessRole). Null = run in-account (the CI/OIDC path)."
  type        = string
  default     = null
}

variable "shared_services_role_arn" {
  description = "Role to assume into shared-services, for the apex zone. Used for prod's site records and for dev/stage NS delegation. Null = the apex zone is local."
  type        = string
  default     = null
}

variable "price_class" {
  description = "CloudFront price class. Non-prod has no reason to pay for edge coverage."
  type        = string
  default     = "PriceClass_100"
}

variable "github_org" {
  description = "GitHub org or user owning the infrastructure repo."
  type        = string
  default     = "steve-cohn-personal"
}

variable "github_repo" {
  description = "Repository name."
  type        = string
  default     = "cohns-net-infra"
}

variable "github_org_id" {
  description = "Numeric GitHub org id, for the immutable OIDC subject. Public; from `gh api users/<org> --jq .id`."
  type        = string
  default     = "195600296"
}

variable "github_repo_id" {
  description = "Numeric GitHub repo id, for the immutable OIDC subject. Public; from `gh api repos/<org>/<repo> --jq .id`."
  type        = string
  default     = "1314380467"
}

variable "deploy_allowed_branches" {
  description = "Branches allowed to deploy to this environment. prod should be empty — it deploys via the environment gate only."
  type        = list(string)
  default     = []
}
