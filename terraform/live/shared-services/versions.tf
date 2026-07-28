terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # State lives in the management-account bucket (one bucket for now). The backend
  # authenticates with whatever ambient creds reach that bucket — run with the mgmt
  # `admin` SSO profile. The PROVIDER below then assumes into shared-services; the
  # backend and the provider authenticate independently, which is what lets state
  # stay in management while resources land in shared-services.
  backend "s3" {
    bucket       = "cohns-tfstate-562995958167"
    key          = "shared-services/terraform.tfstate"
    region       = "us-west-2"
    encrypt      = true
    use_lockfile = true
  }
}

locals {
  tags = {
    Project     = "cohns.net"
    Environment = "shared"
    ManagedBy   = "terraform"
    Repo        = "${var.github_org}/${var.github_repo}"
    Component   = "shared-services"
  }
}

# Assume into the shared-services account from the management-account admin creds.
# The management account can assume OrganizationAccountAccessRole in any member
# account it created; AdministratorAccess grants the sts:AssumeRole to do it.
provider "aws" {
  region = var.region

  assume_role {
    role_arn     = "arn:aws:iam::${var.shared_services_account_id}:role/OrganizationAccountAccessRole"
    session_name = "terraform-shared-services"
  }

  default_tags {
    tags = local.tags
  }
}
