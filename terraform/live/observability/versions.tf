terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    # Observability as code: dashboards, synthetic checks, and the CloudWatch data
    # source are all managed here, not click-opsed in a UI.
    grafana = {
      source  = "grafana/grafana"
      version = "~> 3.0"
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
    Component   = "observability"
  }

  # The public site + API endpoints probed by synthetic monitoring, derived per
  # environment in committed code so the target set can't drift in a gitignored
  # tfvars. Overridable via var.synthetic_targets for a one-off.
  default_synthetic_targets = var.environment == "prod" ? [
    { job = "www", target = "https://www.cohns.net/" },
    { job = "steve", target = "https://steve.cohns.net/" },
    ] : [
    { job = "site-${var.environment}", target = "https://${var.environment}.cohns.net/" },
    { job = "api-${var.environment}", target = "https://api.${var.environment}.cohns.net/healthz" },
  ]

  synthetic_targets = coalesce(var.synthetic_targets, local.default_synthetic_targets)
}

# The workload account whose CloudWatch metrics we read and whose alarms/budget we
# manage (dev owns the live API, ALB, and Aurora). Null = run in-account (CI/OIDC).
provider "aws" {
  region = var.region

  dynamic "assume_role" {
    for_each = var.account_role_arn == null ? [] : [var.account_role_arn]
    content {
      role_arn     = assume_role.value
      session_name = "terraform-observability-${var.environment}"
    }
  }

  default_tags {
    tags = local.tags
  }
}

# AWS Budgets and Cost Explorer live only in us-east-1. A second provider keeps the
# per-account cost budget there while everything else stays regional.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  dynamic "assume_role" {
    for_each = var.account_role_arn == null ? [] : [var.account_role_arn]
    content {
      role_arn     = assume_role.value
      session_name = "terraform-observability-${var.environment}-budget"
    }
  }

  default_tags {
    tags = local.tags
  }
}

# Grafana Cloud. url + auth manage the stack (folders, dashboards, data sources,
# public dashboards); sm_url + sm_access_token manage Synthetic Monitoring. All
# four are supplied at apply time from the environment (TF_VAR_*), never committed:
#
#   export TF_VAR_grafana_auth=...              # stack service-account token
#   export TF_VAR_grafana_sm_access_token=...   # Synthetic Monitoring token
#
# The non-secret url / sm_url live in the gitignored tfvars.
provider "grafana" {
  url             = var.grafana_url
  auth            = var.grafana_auth
  sm_url          = var.grafana_sm_url
  sm_access_token = var.grafana_sm_access_token
}
