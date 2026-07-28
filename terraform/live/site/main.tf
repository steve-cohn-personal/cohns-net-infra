# ---------------------------------------------------------------------------
# The site, in one root module, applied three times.
#
# dev, stage, and prod run *this exact code*. The only things that differ are the
# tfvars file and the backend key:
#
#   terraform init -backend-config=env/dev.backend.hcl
#   terraform apply -var-file=env/dev.tfvars
#
# That's the whole promotion story. If it works in stage it works in prod, because
# it is not a similar configuration — it is the same configuration.
# ---------------------------------------------------------------------------

# --- DNS delegation (dev/stage only) ---------------------------------------
# Non-prod environments own a delegated subzone in their own account. The account
# can write dev.cohns.net all day and has no permission that could touch the apex —
# the account boundary is the blast radius. prod skips this and uses the apex.

resource "aws_route53_zone" "subzone" {
  count = local.is_prod ? 0 : 1

  name    = var.domain_name # dev.cohns.net / stage.cohns.net
  comment = "Delegated subzone for ${var.environment}, owned by the ${var.environment} account."

  tags = local.tags
}

# The delegation itself: an NS record in the apex zone pointing at the subzone's
# nameservers. Written into shared-services via the parent_dns provider.
resource "aws_route53_record" "delegation" {
  count    = local.is_prod ? 0 : 1
  provider = aws.parent_dns

  zone_id = var.apex_zone_id
  name    = var.domain_name
  type    = "NS"
  ttl     = 172800
  records = aws_route53_zone.subzone[0].name_servers
}

locals {
  # prod's records live in the apex; dev/stage's live in the freshly-made subzone.
  site_zone_id = local.is_prod ? var.apex_zone_id : aws_route53_zone.subzone[0].zone_id
}

module "site" {
  source = "../../modules/static-site"

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
    aws.dns       = aws.dns
  }

  domain_name            = var.domain_name
  alternate_domain_names = var.alternate_domain_names
  hosted_zone_id         = local.site_zone_id
  price_class            = var.price_class

  tags = local.tags
}

# The role GitHub Actions assumes to publish content to this environment.
# Note what it can do: sync the origin bucket and invalidate the CDN. Nothing else.
# A compromised pipeline defaces the website; it does not own the account.
module "deploy_role" {
  source = "../../modules/github-oidc"

  github_org     = var.github_org
  github_repo    = var.github_repo
  github_org_id  = var.github_org_id
  github_repo_id = var.github_repo_id
  role_name      = "gha-site-deploy-${var.environment}"

  allowed_branches     = var.deploy_allowed_branches
  allowed_environments = [var.environment]

  create_inline_policy = true
  inline_policy_json   = data.aws_iam_policy_document.deploy.json

  tags = local.tags
}

data "aws_iam_policy_document" "deploy" {
  statement {
    sid    = "SyncSiteContent"
    effect = "Allow"

    actions = [
      "s3:ListBucket",
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
    ]

    resources = [
      module.site.bucket_arn,
      "${module.site.bucket_arn}/*",
    ]
  }

  statement {
    sid    = "InvalidateCdn"
    effect = "Allow"

    actions = [
      "cloudfront:CreateInvalidation",
      "cloudfront:GetInvalidation",
    ]

    resources = [module.site.distribution_arn]
  }
}
