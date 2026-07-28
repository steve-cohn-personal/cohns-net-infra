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

# JWT signing key (HS256): generated, stored in Secrets Manager, injected into the
# container by ECS at launch. Replaces the built-in dev default so no one can forge
# tokens with a known secret. (When Cognito lands, set jwks_url instead and this
# becomes unnecessary.) The generated value lives in state, which is encrypted in
# the management-account bucket — acceptable for a signing key.
resource "random_password" "jwt" {
  length  = 64
  special = false
}

resource "aws_secretsmanager_secret" "jwt" {
  name = "comments-${var.environment}-jwt-secret"
  tags = local.tags
}

resource "aws_secretsmanager_secret_version" "jwt" {
  secret_id     = aws_secretsmanager_secret.jwt.id
  secret_string = random_password.jwt.result
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
    COMMENTS_JWKS_URL           = var.jwks_url
    COMMENTS_CORS_ORIGINS       = jsonencode(var.cors_origins)
  }

  task_policy_arns = [data.terraform_remote_state.data.outputs.db_read_secret_policy_arn]

  # Injected at launch from Secrets Manager, not baked into the image or env.
  secrets = {
    COMMENTS_JWT_SECRET = aws_secretsmanager_secret.jwt.arn
  }

  tags = local.tags
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
