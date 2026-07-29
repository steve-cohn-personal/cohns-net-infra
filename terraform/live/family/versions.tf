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

  # Single-instance (one family library). State in the management-account bucket.
  backend "s3" {
    bucket       = "cohns-tfstate-562995958167"
    key          = "family/terraform.tfstate"
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
    Component = "family"
  }
}

# Assume into the account that hosts the library (prod). Null = run in-account.
provider "aws" {
  region = var.region

  dynamic "assume_role" {
    for_each = var.account_role_arn == null ? [] : [var.account_role_arn]
    content {
      role_arn     = assume_role.value
      session_name = "terraform-family"
    }
  }

  default_tags {
    tags = local.tags
  }
}
