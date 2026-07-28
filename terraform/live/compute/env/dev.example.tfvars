# Copy to dev.tfvars (gitignored) and fill in real values.
# Requires live/data dev applied (VPC + Aurora) and live/site dev applied (subzone).

environment = "dev"
region      = "us-west-2"

account_role_arn     = "arn:aws:iam::<dev-account-id>:role/OrganizationAccountAccessRole"
dns_account_role_arn = "arn:aws:iam::<dev-account-id>:role/OrganizationAccountAccessRole"

# The dev.cohns.net delegated subzone id (from live/site dev output).
hosted_zone_id = "Z0000000000000000000"
domain_name    = "api.dev.cohns.net"

container_image = "<ecr-repo-url>/cohns/comments-api:latest"
