terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"

      # Three provider instances, because this module spans three scopes:
      #   (default)   — the workload account, where the bucket and CDN live
      #   us_east_1   — CloudFront only accepts ACM certs from us-east-1
      #   dns         — the account that owns the hosted zone, which for prod is
      #                 shared-services, not the workload account
      configuration_aliases = [aws.us_east_1, aws.dns]
    }
  }
}
