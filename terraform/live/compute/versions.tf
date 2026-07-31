terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  backend "s3" {}
}

locals {
  tags = {
    Project     = "cohns.net"
    Environment = var.environment
    ManagedBy   = "terraform"
    Repo        = "${var.github_org}/${var.github_repo}"
    Component   = "compute"
  }

  # The site origin(s) allowed to call this API, derived per environment in committed
  # code (not carried in the gitignored tfvars) so it can't drift. Overridable via
  # the cors_origins var for a one-off.
  cors_origins = var.environment == "prod" ? ["https://cohns.net", "https://www.cohns.net"] : ["https://${var.environment}.cohns.net"]
}

# The workload account. Null = run in-account (CI/OIDC).
provider "aws" {
  region = var.region

  dynamic "assume_role" {
    for_each = var.account_role_arn == null ? [] : [var.account_role_arn]
    content {
      role_arn     = assume_role.value
      session_name = "terraform-compute-${var.environment}"
    }
  }

  default_tags {
    tags = local.tags
  }
}

# The account that owns the DNS zone the API record lives in: the env account for
# a delegated subzone (dev/stage), shared-services for the apex (prod).
provider "aws" {
  alias  = "dns"
  region = var.region

  dynamic "assume_role" {
    for_each = var.dns_account_role_arn == null ? [] : [var.dns_account_role_arn]
    content {
      role_arn     = assume_role.value
      session_name = "terraform-compute-${var.environment}-dns"
    }
  }

  default_tags {
    tags = local.tags
  }
}
