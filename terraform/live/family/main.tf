# ---------------------------------------------------------------------------
# live/family — the private family photo library (Phase 3).
#
# A curated, invite-only library: photos live in a fully-private S3 bucket and are
# only ever reachable through short-lived presigned URLs, minted per request for a
# signed-in member of the Cognito `family` group. An HTTP API with a Cognito JWT
# authorizer guards the list endpoint; the site's /family page renders the grid.
#
# Cheap to leave running — HTTP API + Lambda + a little S3 storage, all ~free-tier
# at family scale. Cognito config is read from shared-services (single source).
# ---------------------------------------------------------------------------

data "terraform_remote_state" "shared" {
  backend = "s3"
  config = {
    bucket = "cohns-tfstate-562995958167"
    key    = "shared-services/terraform.tfstate"
    region = "us-west-2"
  }
}

module "library" {
  source = "../../modules/photo-library"

  name              = var.name
  cognito_issuer    = data.terraform_remote_state.shared.outputs.cognito_issuer
  cognito_client_id = data.terraform_remote_state.shared.outputs.cognito_client_id
  cors_origins      = var.cors_origins

  tags = local.tags
}
