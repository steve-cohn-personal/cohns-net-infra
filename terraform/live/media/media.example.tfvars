# Copy to media.auto.tfvars (gitignored, auto-loaded) and fill in the real ARN.
# The media pipeline lives in the account that serves public content (prod).

account_role_arn = "arn:aws:iam::<prod-account-id>:role/OrganizationAccountAccessRole"
