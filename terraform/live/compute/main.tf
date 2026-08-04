# ---------------------------------------------------------------------------
# live/compute — the comments-api on ECS Fargate, per environment.
#
# Reads the data layer (VPC, subnets, DB endpoint + secret) from live/data's
# remote state, mints a regional ACM cert for the API hostname, runs the container
# behind an ALB, and points DNS at it. The task role is granted read on exactly the
# DB secret; the app fetches its own credentials at startup.
#
# NOT applied yet — this is the compute the cost decision gates.
# ---------------------------------------------------------------------------

data "terraform_remote_state" "data" {
  backend = "s3"
  config = {
    bucket = "cohns-tfstate-562995958167"
    key    = "data/${var.environment}/terraform.tfstate"
    region = "us-west-2"
  }
}

# Regional ACM cert for the API hostname (ALB certs are same-region, unlike
# CloudFront). Validated via DNS in the zone that owns the record.
resource "aws_acm_certificate" "api" {
  domain_name       = var.domain_name
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = local.tags
}

resource "aws_route53_record" "cert_validation" {
  provider = aws.dns

  for_each = {
    for opt in aws_acm_certificate.api.domain_validation_options :
    opt.domain_name => {
      name   = opt.resource_record_name
      type   = opt.resource_record_type
      record = opt.resource_record_value
    }
  }

  zone_id         = var.hosted_zone_id
  name            = each.value.name
  type            = each.value.type
  records         = [each.value.record]
  ttl             = 60
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "api" {
  certificate_arn         = aws_acm_certificate.api.arn
  validation_record_fqdns = [for r in aws_route53_record.cert_validation : r.fqdn]
}

# Cognito (shared-services) is the token issuer. The app verifies tokens via the
# pool's JWKS (RS256) — no shared HS256 secret to generate, store, or inject.
data "terraform_remote_state" "shared" {
  backend = "s3"
  config = {
    bucket = "cohns-tfstate-562995958167"
    key    = "shared-services/terraform.tfstate"
    region = "us-west-2"
  }
}

module "service" {
  source = "../../modules/fargate-service"

  name   = "comments-${var.environment}"
  region = var.region

  vpc_id            = data.terraform_remote_state.data.outputs.vpc_id
  public_subnet_ids = data.terraform_remote_state.data.outputs.public_subnet_ids

  image            = var.container_image
  enable_https     = true
  certificate_arn  = aws_acm_certificate_validation.api.certificate_arn
  desired_count    = var.desired_count
  cpu_architecture = var.cpu_architecture

  # The app reads its DB password from Secrets Manager itself (task role below);
  # only non-secret settings are passed as plain env.
  environment = {
    COMMENTS_DB_SECRET_ARN      = data.terraform_remote_state.data.outputs.db_secret_arn
    COMMENTS_DB_HOST            = data.terraform_remote_state.data.outputs.db_endpoint
    COMMENTS_DB_PORT            = "5432"
    COMMENTS_DB_NAME            = data.terraform_remote_state.data.outputs.db_name
    COMMENTS_AWS_REGION         = var.region
    COMMENTS_AUTO_CREATE_TABLES = tostring(var.auto_create_tables)
    COMMENTS_DB_NULLPOOL        = tostring(var.db_nullpool)
    # Verify Cognito-issued tokens (RS256 via JWKS). Audience = the app client id
    # (ID tokens carry it); issuer pins the pool.
    COMMENTS_JWKS_URL     = data.terraform_remote_state.shared.outputs.cognito_jwks_url
    COMMENTS_JWT_ISSUER   = data.terraform_remote_state.shared.outputs.cognito_issuer
    COMMENTS_JWT_AUDIENCE = data.terraform_remote_state.shared.outputs.cognito_client_id
    COMMENTS_CORS_ORIGINS = jsonencode(coalesce(var.cors_origins, local.cors_origins))
    # User administration: the pool + the cross-account role the task assumes to
    # grant/revoke group membership, and the topic it publishes access requests to.
    COMMENTS_COGNITO_POOL_ID          = data.terraform_remote_state.shared.outputs.cognito_user_pool_id
    COMMENTS_COGNITO_ADMIN_ROLE_ARN   = data.terraform_remote_state.shared.outputs.cognito_user_admin_role_arn
    COMMENTS_ACCESS_REQUEST_TOPIC_ARN = aws_sns_topic.access_requests.arn
  }

  task_policy_arns = [
    data.terraform_remote_state.data.outputs.db_read_secret_policy_arn,
    aws_iam_policy.task_admin.arn,
  ]

  tags = local.tags
}

# --- Access requests + user admin -------------------------------------------

# Emails the moderators when someone asks for access. Email subscriptions require
# a one-time confirmation click per address.
resource "aws_sns_topic" "access_requests" {
  name = "comments-${var.environment}-access-requests"
  tags = local.tags
}

resource "aws_sns_topic_subscription" "access_requests_email" {
  for_each  = toset(var.access_request_emails)
  topic_arn = aws_sns_topic.access_requests.arn
  protocol  = "email"
  endpoint  = each.value
}

# The task may assume the scoped Cognito-admin role (in shared-services) and publish
# to its own access-request topic. Nothing broader.
data "aws_iam_policy_document" "task_admin" {
  statement {
    sid       = "AssumeCognitoAdmin"
    effect    = "Allow"
    actions   = ["sts:AssumeRole"]
    resources = [data.terraform_remote_state.shared.outputs.cognito_user_admin_role_arn]
  }
  statement {
    sid       = "PublishAccessRequests"
    effect    = "Allow"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.access_requests.arn]
  }
}

resource "aws_iam_policy" "task_admin" {
  name   = "comments-${var.environment}-user-admin"
  policy = data.aws_iam_policy_document.task_admin.json
  tags   = local.tags
}

resource "aws_route53_record" "api" {
  provider = aws.dns

  zone_id = var.hosted_zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = module.service.alb_dns_name
    zone_id                = module.service.alb_zone_id
    evaluate_target_health = true
  }
}
