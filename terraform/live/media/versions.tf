terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }

  # Single-instance (one media pipeline). State in the management-account bucket.
  backend "s3" {
    bucket       = "cohns-tfstate-562995958167"
    key          = "media/terraform.tfstate"
    region       = "us-west-2"
    encrypt      = true
    use_lockfile = true
  }
}

locals {
  tags = {
    Project   = "cohns.net"
    ManagedBy = "terraform"
    Repo      = "${var.github_org}/${var.github_repo}"
    Component = "media"
  }
}

# Assume into the account that hosts public media (prod). Null = run in-account.
provider "aws" {
  region = var.region

  dynamic "assume_role" {
    for_each = var.account_role_arn == null ? [] : [var.account_role_arn]
    content {
      role_arn     = assume_role.value
      session_name = "terraform-media"
    }
  }

  default_tags {
    tags = local.tags
  }
}

# CloudFront reads its certificate from us-east-1 only. Same account as default.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  dynamic "assume_role" {
    for_each = var.account_role_arn == null ? [] : [var.account_role_arn]
    content {
      role_arn     = assume_role.value
      session_name = "terraform-media-use1"
    }
  }

  default_tags {
    tags = local.tags
  }
}

# The apex zone lives in shared-services; assume there to write media.cohns.net.
provider "aws" {
  alias  = "dns"
  region = var.region

  dynamic "assume_role" {
    for_each = var.dns_account_role_arn == null ? [] : [var.dns_account_role_arn]
    content {
      role_arn     = assume_role.value
      session_name = "terraform-media-dns"
    }
  }

  default_tags {
    tags = local.tags
  }
}
