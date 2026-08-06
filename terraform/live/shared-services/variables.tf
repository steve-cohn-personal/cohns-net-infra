variable "region" {
  description = "Region for the provider. Route53 is global; this only signs the API calls."
  type        = string
  default     = "us-west-2"
}

variable "shared_services_account_id" {
  description = "The shared-services account id (from live/org outputs). The provider assumes into it."
  type        = string
  default     = "004161356168"
}

variable "domain_name" {
  description = "The apex domain. Its public hosted zone is the root of all DNS for the project."
  type        = string
  default     = "cohns.net"
}

variable "prod_account_id" {
  description = "The prod account id. Route53WriterFromProd trusts this account so prod can manage its own apex records. Supplied via gitignored prod.auto.tfvars — workload account IDs stay out of the public repo."
  type        = string
}

variable "prod_record_labels" {
  description = "Labels under the apex that prod is allowed to manage (e.g. www, steve). The scoped role can touch these and their ACM validation records, nothing else in the zone."
  type        = list(string)
  default     = ["www", "steve"]
}

# --- CloudTrail log archive -----------------------------------------------
# The org trail itself is created in the management account (live/org). These let
# the bucket policy grant exactly that trail write access. Defaults are the real
# values; they are not secrets.

variable "management_account_id" {
  description = "Management account id — the org trail lives there and writes the mgmt account's own logs under its account-id path."
  type        = string
  default     = "562995958167"
}

variable "organization_id" {
  description = "AWS Organization id — member-account logs are written under this path in the bucket."
  type        = string
  default     = "o-ajlh1xjt64"
}

variable "cloudtrail_name" {
  description = "Name of the org trail in the management account. Must match live/org."
  type        = string
  default     = "cohns-org-trail"
}

variable "cloudtrail_home_region" {
  description = "Region the org trail is created in (live/org's provider region). Sets the region in the trail ARN the bucket policy trusts."
  type        = string
  default     = "us-west-2"
}

# auth.js uses redirect_uri = location.origin + "/", so every origin the site is
# served from must be a registered callback AND logout URL — including the apex,
# which began serving the site directly on 2026-08-02.
variable "auth_callback_urls" {
  description = "OAuth callback URLs for the Cognito web client (site origins + local dev)."
  type        = list(string)
  default = [
    "https://cohns.net/",
    "https://www.cohns.net/",
    "https://steve.cohns.net/",
    "https://dev.cohns.net/",
    "https://stage.cohns.net/",
    "http://localhost:5173/",
  ]
}

variable "auth_logout_urls" {
  description = "Post-logout redirect URLs for the Cognito web client (every site origin)."
  type        = list(string)
  default = [
    "https://cohns.net/",
    "https://www.cohns.net/",
    "https://steve.cohns.net/",
    "https://dev.cohns.net/",
    "https://stage.cohns.net/",
    "http://localhost:5173/",
  ]
}

variable "github_org" {
  description = "GitHub org/owner, used for the Repo tag and the ECR-push OIDC trust."
  type        = string
  default     = "steve-cohn-personal"
}

variable "github_org_id" {
  description = "Numeric GitHub org id, for the immutable OIDC subject. Public."
  type        = string
  default     = "195600296"
}

variable "github_repo_id" {
  description = "Numeric GitHub repo id, for the immutable OIDC subject. Public."
  type        = string
  default     = "1314380467"
}

variable "github_repo" {
  description = "GitHub repo name, used only for the Repo tag."
  type        = string
  default     = "cohns-net-infra"
}
