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

# Media uploads (prod only — the media stack is in this account). Enables the
# presigned-PUT endpoint and the scoped s3:PutObject task-role grant. Bucket names
# are cohns-media-{output,ingest}-<prod-account-id>. Leave unset in dev/stage.
media_output_bucket = "cohns-media-output-<prod-account-id>"
media_ingest_bucket = "cohns-media-ingest-<prod-account-id>"
media_cdn_base      = "https://media.cohns.net"
