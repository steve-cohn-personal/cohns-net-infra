# ---------------------------------------------------------------------------
# Media pipeline: upload -> transcode -> serve.
#
#   ingest bucket  --(ObjectCreated)-->  Lambda  --submits-->  MediaConvert
#                                                                    |
#   CloudFront (OAC)  <--serves--  output bucket  <--HLS/MP4/thumb---+
#
# Idle cost is essentially zero — MediaConvert bills per minute transcoded, only
# when a job runs; the buckets, Lambda, and CloudFront are pennies/free-tier.
# ---------------------------------------------------------------------------

data "aws_caller_identity" "current" {}

locals {
  ingest_bucket = "${var.name}-ingest-${data.aws_caller_identity.current.account_id}"
  output_bucket = "${var.name}-output-${data.aws_caller_identity.current.account_id}"
}

# --- Buckets ----------------------------------------------------------------

resource "aws_s3_bucket" "ingest" {
  bucket = local.ingest_bucket
  tags   = var.tags
}

resource "aws_s3_bucket_public_access_block" "ingest" {
  bucket                  = aws_s3_bucket.ingest.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Raw uploads are large and only needed until transcoded — expire them.
resource "aws_s3_bucket_lifecycle_configuration" "ingest" {
  bucket = aws_s3_bucket.ingest.id
  rule {
    id     = "expire-raw-uploads"
    status = "Enabled"
    filter {}
    expiration { days = 30 }
    abort_incomplete_multipart_upload { days_after_initiation = 7 }
  }
}

resource "aws_s3_bucket" "output" {
  bucket = local.output_bucket
  tags   = var.tags
}

resource "aws_s3_bucket_public_access_block" "output" {
  bucket                  = aws_s3_bucket.output.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# --- MediaConvert role (reads ingest, writes output) ------------------------

data "aws_iam_policy_document" "mediaconvert_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["mediaconvert.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "mediaconvert" {
  name               = "${var.name}-mediaconvert"
  assume_role_policy = data.aws_iam_policy_document.mediaconvert_assume.json
  tags               = var.tags
}

data "aws_iam_policy_document" "mediaconvert" {
  statement {
    sid       = "ReadIngest"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.ingest.arn}/*"]
  }
  statement {
    sid       = "WriteOutput"
    effect    = "Allow"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.output.arn}/*"]
  }
}

resource "aws_iam_role_policy" "mediaconvert" {
  name   = "${var.name}-mediaconvert"
  role   = aws_iam_role.mediaconvert.id
  policy = data.aws_iam_policy_document.mediaconvert.json
}

# --- Job-submit Lambda ------------------------------------------------------

data "archive_file" "lambda" {
  type        = "zip"
  source_file = "${path.module}/lambda/handler.py"
  output_path = "${path.module}/lambda/handler.zip"
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${var.name}-submit"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
  tags               = var.tags
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.name}-submit"
  retention_in_days = var.lambda_log_retention_days
  tags              = var.tags
}

data "aws_iam_policy_document" "lambda" {
  statement {
    sid       = "SubmitJobs"
    effect    = "Allow"
    actions   = ["mediaconvert:CreateJob", "mediaconvert:DescribeEndpoints", "mediaconvert:GetJob"]
    resources = ["*"] # DescribeEndpoints has no resource scope
  }
  # Hand the MediaConvert role to the service, and only that service.
  statement {
    sid       = "PassMediaConvertRole"
    effect    = "Allow"
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.mediaconvert.arn]
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["mediaconvert.amazonaws.com"]
    }
  }
  statement {
    sid       = "Logs"
    effect    = "Allow"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.lambda.arn}:*"]
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "${var.name}-submit"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda.json
}

resource "aws_lambda_function" "submit" {
  function_name    = "${var.name}-submit"
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.12"
  handler          = "handler.handler"
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256
  timeout          = 30

  # AWS_REGION is provided by the Lambda runtime; don't set it (reserved).
  environment {
    variables = {
      MEDIACONVERT_ROLE_ARN = aws_iam_role.mediaconvert.arn
      OUTPUT_BUCKET         = aws_s3_bucket.output.id
    }
  }

  depends_on = [aws_iam_role_policy.lambda, aws_cloudwatch_log_group.lambda]
  tags       = var.tags
}

resource "aws_lambda_permission" "s3_invoke" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.submit.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.ingest.arn
}

resource "aws_s3_bucket_notification" "ingest" {
  bucket = aws_s3_bucket.ingest.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.submit.arn
    events              = ["s3:ObjectCreated:*"]
  }

  depends_on = [aws_lambda_permission.s3_invoke]
}

# --- CloudFront for playback ------------------------------------------------

resource "aws_cloudfront_origin_access_control" "output" {
  name                              = "${var.name}-output-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# HLS players fetch segments cross-origin from the site, so CORS must be allowed.
resource "aws_cloudfront_response_headers_policy" "cors" {
  name = "${var.name}-cors"

  cors_config {
    origin_override                  = true
    access_control_allow_credentials = false

    access_control_allow_headers { items = ["*"] }
    access_control_allow_methods { items = ["GET", "HEAD", "OPTIONS"] }
    access_control_allow_origins { items = var.cors_origins }
  }
}

resource "aws_cloudfront_distribution" "media" {
  enabled         = true
  is_ipv6_enabled = true
  comment         = "${var.name} media"
  price_class     = "PriceClass_100"

  origin {
    domain_name              = aws_s3_bucket.output.bucket_regional_domain_name
    origin_id                = "s3-output"
    origin_access_control_id = aws_cloudfront_origin_access_control.output.id
  }

  default_cache_behavior {
    target_origin_id           = "s3-output"
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD", "OPTIONS"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = data.aws_cloudfront_cache_policy.optimized.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.cors.id
  }

  restrictions {
    geo_restriction { restriction_type = "none" }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = var.tags
}

data "aws_cloudfront_cache_policy" "optimized" {
  name = "Managed-CachingOptimized"
}

# Only this distribution may read the output bucket.
data "aws_iam_policy_document" "output" {
  statement {
    sid    = "AllowCloudFrontOAC"
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.output.arn}/*"]
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.media.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "output" {
  bucket     = aws_s3_bucket.output.id
  policy     = data.aws_iam_policy_document.output.json
  depends_on = [aws_s3_bucket_public_access_block.output]
}
