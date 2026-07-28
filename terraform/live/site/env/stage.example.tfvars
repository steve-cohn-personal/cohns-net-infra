# Stage. Production-shaped. Copy to stage.tfvars (gitignored) and fill in real IDs.
# Owns its own delegated stage.cohns.net subzone, so DNS mistakes here cannot touch
# the apex.

environment = "stage"
region      = "us-west-2"

domain_name            = "stage.cohns.net"
alternate_domain_names = []

apex_zone_id = "ZXXXXXXXXXXXXXXXXXXXX"

account_role_arn         = "arn:aws:iam::<stage-account-id>:role/OrganizationAccountAccessRole"
shared_services_role_arn = "arn:aws:iam::<shared-services-account-id>:role/OrganizationAccountAccessRole"

price_class = "PriceClass_100"

# Empty: stage deploys through the `stage` GitHub Environment, not from a branch.
deploy_allowed_branches = []
