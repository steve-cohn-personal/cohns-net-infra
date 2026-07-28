terraform {
  # 1.10 is the floor: native S3 state locking (`use_lockfile`) landed there.
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # First apply ran with local state; state was then migrated here with
  # `terraform init -migrate-state`. See docs/bootstrap.md.
  #
  # NOTE: state lives in the management account (562995958167), not shared-services
  # — that account doesn't exist yet, and org/foundational state belongs with the
  # Org it manages. Workload state can move to shared-services later.
  backend "s3" {
    bucket       = "cohns-tfstate-562995958167"
    key          = "bootstrap/terraform.tfstate"
    region       = "us-west-2"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = var.tags
  }
}
