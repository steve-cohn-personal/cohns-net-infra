# Copy to dev.backend.hcl (gitignored) and fill in the bucket:
#   terraform init -reconfigure -backend-config=env/dev.backend.hcl
# All three environments share one bucket (in the management account, from
# bootstrap/) and differ only by key — one place to look for state.

bucket = "cohns-tfstate-<management-account-id>"
key    = "site/dev/terraform.tfstate"
region = "us-west-2"

encrypt      = true
use_lockfile = true
