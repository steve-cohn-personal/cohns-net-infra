# ---------------------------------------------------------------------------
# live/media — the cooking-lesson video pipeline (Phase 3).
#
# One pipeline for the whole site's media, served from a custom domain
# (media.cohns.net). Upload a lesson video to the ingest bucket; it's transcoded
# to HLS + a thumbnail and served from CloudFront. A recipe's `video_key` points
# at the output prefix.
#
# Cheap to leave running — MediaConvert only bills while a job runs.
# ---------------------------------------------------------------------------

# CloudFront cert must be in us-east-1. Validated via DNS in the apex zone.
resource "aws_acm_certificate" "media" {
  provider = aws.us_east_1

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
    for opt in aws_acm_certificate.media.domain_validation_options :
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

resource "aws_acm_certificate_validation" "media" {
  provider = aws.us_east_1

  certificate_arn         = aws_acm_certificate.media.arn
  validation_record_fqdns = [for r in aws_route53_record.cert_validation : r.fqdn]
}

module "media" {
  source = "../../modules/media-pipeline"

  name            = var.name
  cors_origins    = var.cors_origins
  domain_name     = var.domain_name
  certificate_arn = aws_acm_certificate_validation.media.certificate_arn

  tags = local.tags
}

resource "aws_route53_record" "media" {
  provider = aws.dns

  zone_id = var.hosted_zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = module.media.media_cdn_domain
    zone_id                = module.media.cloudfront_hosted_zone_id
    evaluate_target_health = false
  }
}
