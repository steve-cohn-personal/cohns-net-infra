# Copy to prod.tfvars (gitignored) and fill in real values.
# Requires live/data prod applied (VPC + Aurora). api.cohns.net lives in the apex
# zone (shared-services), so the DNS role assumes into shared-services, not prod.

environment = "prod"
region      = "us-west-2"

account_role_arn     = "arn:aws:iam::<prod-account-id>:role/OrganizationAccountAccessRole"
dns_account_role_arn = "arn:aws:iam::<shared-services-account-id>:role/OrganizationAccountAccessRole"

# The apex zone id (shared-services), where api.cohns.net is published.
hosted_zone_id = "Z0000000000000000000"
domain_name    = "api.cohns.net"

container_image = "<ecr-repo-url>/cohns/comments-api:latest"

db_nullpool = true
