# Backend config for prod. Copy to prod.backend.hcl (gitignored) and fill in the
# bucket:
#   terraform init -reconfigure -backend-config=env/prod.backend.hcl
#
# All three environments share one bucket (in the management account, from
# bootstrap/) and differ only by key. One place to look for state; no chance of a
# workspace mix-up.

bucket = "cohns-tfstate-<management-account-id>"
key    = "site/prod/terraform.tfstate"
region = "us-west-2"

encrypt      = true
use_lockfile = true
