# Dev. Copy to dev.tfvars (gitignored) and fill in real IDs. Where things get broken.

environment = "dev"
region      = "us-west-2"

domain_name            = "dev.cohns.net"
alternate_domain_names = []

# The cohns.net apex zone in shared-services (from live/shared-services output).
# dev gets an NS delegation record here and its own dev.cohns.net subzone.
apex_zone_id = "ZXXXXXXXXXXXXXXXXXXXX"

# Cross-account run from mgmt admin: assume into the dev account for the workload,
# and into shared-services to write the NS delegation record. Leave both null to
# run in-account (the CI/OIDC path).
account_role_arn         = "arn:aws:iam::<dev-account-id>:role/OrganizationAccountAccessRole"
shared_services_role_arn = "arn:aws:iam::<shared-services-account-id>:role/OrganizationAccountAccessRole"

price_class = "PriceClass_100"

# dev auto-deploys on merge to main. That's the point of dev.
deploy_allowed_branches = ["main"]
