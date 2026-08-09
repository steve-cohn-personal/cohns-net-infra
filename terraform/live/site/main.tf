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

  # The content API this environment's site talks to (prod = apex host).
  api_origin = local.is_prod ? "https://api.cohns.net" : "https://api.${var.environment}.cohns.net"

  # The site's Content-Security-Policy is derived here, in committed code, rather
  # than carried in the gitignored tfvars — it's a public response header, not a
  # secret, and keeping it in tfvars let local and CI drift (CI, lacking the value,
  # reverted the deployed policy to the module's strict default). Only api_origin
  # varies by environment; the media CDN, Cognito hosted-UI, and family library
  # (its API + private-photo presigned URLs from the regional S3 endpoint) are shared.
  content_security_policy = join("; ", [
    "default-src 'self'",
    "img-src 'self' data: https://media.cohns.net https://cohns-family-810100780414.s3.us-west-2.amazonaws.com",
    "style-src 'self'",
    "script-src 'self'",
    # The media bucket S3 endpoints are here (not just media.cohns.net) because
    # moderators upload recipe images/videos via a presigned PUT straight to the
    # bucket's regional endpoint — a fetch(), so connect-src governs it.
    "connect-src 'self' ${local.api_origin} https://media.cohns.net https://cohns-media-output-810100780414.s3.us-west-2.amazonaws.com https://cohns-media-ingest-810100780414.s3.us-west-2.amazonaws.com https://cohns-net-auth.auth.us-west-2.amazoncognito.com https://soweh7qos7.execute-api.us-west-2.amazonaws.com",
    "media-src 'self' blob: https://media.cohns.net",
    # No frame-src: the /observability page links out to the Grafana Cloud public
    # dashboard rather than embedding it (Grafana Cloud sends X-Frame-Options:
    # deny and cannot be configured to allow framing). If it ever can, re-add
    # "frame-src https://*.grafana.net" here alongside the iframe swap in
    # site/js/observability.js. frame-ancestors 'none' below still blocks anyone
    # from embedding this site.
    "object-src 'none'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
  ])
}

module "site" {
  source = "../../modules/static-site"

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
    aws.dns       = aws.dns
  }

  domain_name             = var.domain_name
  alternate_domain_names  = var.alternate_domain_names
  hosted_zone_id          = local.site_zone_id
  price_class             = var.price_class
  content_security_policy = coalesce(var.content_security_policy, local.content_security_policy)

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
