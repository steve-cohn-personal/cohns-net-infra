# Copy to media.auto.tfvars (gitignored, auto-loaded) and fill in the real ARNs.
# Media lives in the account that serves public content (prod); the apex zone it
# writes media.cohns.net into lives in shared-services.

account_role_arn     = "arn:aws:iam::<prod-account-id>:role/OrganizationAccountAccessRole"
dns_account_role_arn = "arn:aws:iam::<shared-services-account-id>:role/OrganizationAccountAccessRole"
