terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # Deliberately empty. Filled per-environment at init time:
  #   terraform init -reconfigure -backend-config=env/prod.backend.hcl
  # This is what lets one root module own three state files.
  backend "s3" {}
}

locals {
  is_prod = var.environment == "prod"

  tags = {
    Project     = "cohns.net"
    Environment = var.environment
    ManagedBy   = "terraform"
    Repo        = "${var.github_org}/${var.github_repo}"
  }

  # Where the SITE's own records (ACM validation + alias A/AAAA) are written:
  #   prod      -> the apex zone, owned by shared-services
  #   dev/stage -> the delegated subzone, local to the workload account
  # so the DNS provider assumes into shared-services for prod, the env account otherwise.
  dns_role_arn = local.is_prod ? var.shared_services_role_arn : var.account_role_arn
}

# The workload account (dev/stage/prod). Assumed into from the mgmt admin creds the
# CLI/CI is authenticated as. When account_role_arn is null the assume_role block
# disappears and this is simply the local account (that is the CI/OIDC path).
provider "aws" {
  region = var.region

  dynamic "assume_role" {
    for_each = var.account_role_arn == null ? [] : [var.account_role_arn]
    content {
      role_arn     = assume_role.value
      session_name = "terraform-site-${var.environment}"
    }
  }

  default_tags {
    tags = local.tags
  }
}

# CloudFront reads certificates from us-east-1 only. Same account as the default.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  dynamic "assume_role" {
    for_each = var.account_role_arn == null ? [] : [var.account_role_arn]
    content {
      role_arn     = assume_role.value
      session_name = "terraform-site-${var.environment}-use1"
    }
  }

  default_tags {
    tags = local.tags
  }
}

# The account that owns the zone the site's records live in (env account for
# dev/stage, shared-services for prod).
provider "aws" {
  alias  = "dns"
  region = var.region

  dynamic "assume_role" {
    for_each = local.dns_role_arn == null ? [] : [local.dns_role_arn]
    content {
      role_arn     = assume_role.value
      session_name = "terraform-site-${var.environment}-dns"
    }
  }

  default_tags {
    tags = local.tags
  }
}

# The apex zone in shared-services, used only to write the NS delegation record for
# a non-prod subzone. prod does not use this (it writes the apex via aws.dns).
provider "aws" {
  alias  = "parent_dns"
  region = var.region

  dynamic "assume_role" {
    for_each = var.shared_services_role_arn == null ? [] : [var.shared_services_role_arn]
    content {
      role_arn     = assume_role.value
      session_name = "terraform-site-${var.environment}-parentdns"
    }
  }

  default_tags {
    tags = local.tags
  }
}
