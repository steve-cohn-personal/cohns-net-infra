# ---------------------------------------------------------------------------
# Organization CloudTrail.
#
# One multi-region trail in the management account, capturing management events
# from every account in the org (is_organization_trail = true) and writing them to
# the locked archive bucket in shared-services (created by live/shared-services).
#
# Trusted access for cloudtrail.amazonaws.com is already enabled on the org (see
# aws_organizations_organization.this), which is what allows an org trail to exist.
# The SCP guardrail-protect-foundation stops member accounts from stopping or
# deleting it.
# ---------------------------------------------------------------------------

resource "aws_cloudtrail" "org" {
  name           = var.cloudtrail_name
  s3_bucket_name = var.cloudtrail_bucket_name

  is_organization_trail         = true
  is_multi_region_trail         = true
  include_global_service_events = true
  enable_log_file_validation    = true
  enable_logging                = true

  tags = local.tags
}

output "cloudtrail_arn" {
  description = "ARN of the organization trail."
  value       = aws_cloudtrail.org.arn
}
