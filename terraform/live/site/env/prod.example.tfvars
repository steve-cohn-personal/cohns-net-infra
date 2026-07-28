# Production. Copy to prod.tfvars (gitignored) and fill in real IDs.
# prod is the only environment that carries the apex names and writes the apex zone
# in shared-services directly — no delegated subzone.

environment = "prod"
region      = "us-west-2"

domain_name            = "www.cohns.net"
alternate_domain_names = ["steve.cohns.net"]

apex_zone_id = "ZXXXXXXXXXXXXXXXXXXXX"

account_role_arn         = "arn:aws:iam::<prod-account-id>:role/OrganizationAccountAccessRole"
shared_services_role_arn = "arn:aws:iam::<shared-services-account-id>:role/OrganizationAccountAccessRole"

price_class = "PriceClass_100"

# Empty on purpose. prod deploys only through the gated `prod` GitHub Environment,
# which has a required reviewer. That approval click is the promotion gate.
deploy_allowed_branches = []
