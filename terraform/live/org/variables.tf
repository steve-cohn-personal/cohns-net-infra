variable "region" {
  description = "Region for the management-account provider. Organizations is global; this only affects where API calls are signed."
  type        = string
  default     = "us-west-2"
}

variable "name_prefix" {
  description = "Prefix for account names, matching the existing management account (cohns-billing)."
  type        = string
  default     = "cohns"
}

variable "cloudtrail_name" {
  description = "Name of the org trail. Must match what live/shared-services trusts in the bucket policy."
  type        = string
  default     = "cohns-org-trail"
}

variable "cloudtrail_bucket_name" {
  description = "The log-archive bucket in shared-services (from its cloudtrail_bucket_name output)."
  type        = string
  default     = "cohns-cloudtrail-004161356168"
}

variable "github_org" {
  description = "GitHub org/owner, used only for the Repo tag."
  type        = string
  default     = "steve-cohn-personal"
}

variable "github_repo" {
  description = "GitHub repo name, used only for the Repo tag."
  type        = string
  default     = "cohns-net-infra"
}

# Member-account root emails. Each AWS account needs a globally-unique email, and
# it is the account's root identity and recovery address — so these are supplied
# from a gitignored org.auto.tfvars, never committed to this public repo.
# See org.example.tfvars for the expected shape.
variable "account_emails" {
  description = "Map of member-account short name (shared-services|dev|stage|prod) to its unique root email."
  type        = map(string)

  validation {
    condition = alltrue([
      for k in ["shared-services", "dev", "stage", "prod"] : contains(keys(var.account_emails), k)
    ])
    error_message = "account_emails must define all of: shared-services, dev, stage, prod."
  }

  validation {
    condition     = length(distinct(values(var.account_emails))) == length(values(var.account_emails))
    error_message = "Every member account needs a distinct email; AWS rejects duplicates."
  }
}
