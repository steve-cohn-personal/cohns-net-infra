# Copy to prod.tfvars (gitignored) and fill in the real account role ARN.

environment = "prod"
region      = "us-west-2"

account_role_arn = "arn:aws:iam::<prod-account-id>:role/OrganizationAccountAccessRole"

vpc_cidr = "10.20.0.0/16" # distinct from dev's 10.10.0.0/16

min_acu = 0 # scale to zero when idle
max_acu = 2

# prod-safe: keep a final snapshot on destroy and guard against accidental deletion.
skip_final_snapshot = false
deletion_protection = true
