terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # State in the management-account bucket, filled per environment at init:
  #   terraform init -reconfigure -backend-config=env/dev.backend.hcl
  backend "s3" {}
}

locals {
  tags = {
    Project     = "cohns.net"
    Environment = var.environment
    ManagedBy   = "terraform"
    Repo        = "${var.github_org}/${var.github_repo}"
    Component   = "data"
  }
}

# Assume into the environment's workload account. Null = run in-account (CI/OIDC).
provider "aws" {
  region = var.region

  dynamic "assume_role" {
    for_each = var.account_role_arn == null ? [] : [var.account_role_arn]
    content {
      role_arn     = assume_role.value
      session_name = "terraform-data-${var.environment}"
    }
  }

  default_tags {
    tags = local.tags
  }
}
