# ---------------------------------------------------------------------------
# live/data — the per-environment data plane: a private VPC and an Aurora
# Serverless v2 Postgres cluster for the comments service.
#
# One root module, applied per environment like live/site. dev is disposable and
# scales to zero; prod would raise the ACU floor, enable deletion protection, and
# keep final snapshots (via its tfvars).
# ---------------------------------------------------------------------------

module "network" {
  source = "../../modules/network"

  name = "cohns-${var.environment}"
  cidr = var.vpc_cidr

  tags = local.tags
}

module "db" {
  source = "../../modules/aurora-serverless"

  name       = "comments-${var.environment}"
  vpc_id     = module.network.vpc_id
  subnet_ids = module.network.private_subnet_ids

  # Reachable from within the VPC for now; tighten to the app security group once
  # the compute platform lands here.
  allowed_ingress_cidrs = [module.network.vpc_cidr]

  database_name = var.database_name

  min_acu             = var.min_acu
  max_acu             = var.max_acu
  skip_final_snapshot = var.skip_final_snapshot
  deletion_protection = var.deletion_protection

  tags = local.tags
}
