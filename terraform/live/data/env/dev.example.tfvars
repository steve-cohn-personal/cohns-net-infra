# Copy to dev.tfvars (gitignored) and fill in the real account role ARN.

environment = "dev"
region      = "us-west-2"

account_role_arn = "arn:aws:iam::<dev-account-id>:role/OrganizationAccountAccessRole"

vpc_cidr = "10.10.0.0/16"

min_acu = 0 # scale to zero when idle
max_acu = 2

skip_final_snapshot = true
deletion_protection = false
