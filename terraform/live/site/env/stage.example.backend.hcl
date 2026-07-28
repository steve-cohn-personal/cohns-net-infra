# Copy to stage.backend.hcl (gitignored) and fill in the bucket:
#   terraform init -reconfigure -backend-config=env/stage.backend.hcl

bucket = "cohns-tfstate-<management-account-id>"
key    = "site/stage/terraform.tfstate"
region = "us-west-2"

encrypt      = true
use_lockfile = true
