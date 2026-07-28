terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # Single-instance root module (there is only one Organization), so the backend
  # is hardcoded rather than filled per-environment like live/site. State lives in
  # the management-account bucket created by bootstrap/, under its own key.
  backend "s3" {
    bucket       = "cohns-tfstate-562995958167"
    key          = "org/terraform.tfstate"
    region       = "us-west-2"
    encrypt      = true
    use_lockfile = true
  }
}

locals {
  # No Environment tag here — the Organization spans all environments.
  tags = {
    Project   = "cohns.net"
    ManagedBy = "terraform"
    Repo      = "${var.github_org}/${var.github_repo}"
    Component = "org"
  }
}

# Runs with SSO admin credentials in the management account. The Organizations and
# Identity Center control planes live in the management account; there is no
# assume_role here because this IS that account.
provider "aws" {
  region = var.region

  default_tags {
    tags = local.tags
  }
}

# IAM Identity Center is regional, and its home region is us-east-1 (chosen when it
# was enabled). All ssoadmin/identitystore calls must target that region, not the
# us-west-2 default above.
provider "aws" {
  alias  = "identity"
  region = "us-east-1"

  default_tags {
    tags = local.tags
  }
}
