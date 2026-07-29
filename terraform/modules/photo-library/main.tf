# ---------------------------------------------------------------------------
# Private family photo library.
#
#   site /family/  --ID token-->  API Gateway (Cognito JWT authorizer)
#                                        |  validates the token at the edge
#                                        v
#                                     Lambda  --checks cognito:groups ⊇ family
#                                        |     --> S3 presigned URLs (short TTL)
#   browser  <--thumbs/full images--  S3 (fully private, nothing public)
#
# The bucket is never public and there is no CloudFront in front of it — access is
# always a freshly-signed, expiring URL minted per request for an authenticated
# family member. Idle cost is essentially zero (HTTP API + Lambda + a little S3).
# ---------------------------------------------------------------------------

data "aws_caller_identity" "current" {}

locals {
  bucket_name = "${var.name}-${data.aws_caller_identity.current.account_id}"
}

# --- Private bucket ---------------------------------------------------------

resource "aws_s3_bucket" "photos" {
  bucket = local.bucket_name
  tags   = var.tags
}

resource "aws_s3_bucket_public_access_block" "photos" {
  bucket                  = aws_s3_bucket.photos.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "photos" {
  bucket = aws_s3_bucket.photos.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_versioning" "photos" {
  bucket = aws_s3_bucket.photos.id
  versioning_configuration { status = "Enabled" }
}

# Versioning keeps a curated re-populate safe (an accidental overwrite is
# recoverable), but the populate script syncs with --delete, so every re-run would
# otherwise leave the replaced objects lingering as noncurrent versions forever.
# Expire them after a short grace window, and clean up incomplete multipart uploads.
resource "aws_s3_bucket_lifecycle_configuration" "photos" {
  bucket = aws_s3_bucket.photos.id

  rule {
    id     = "expire-noncurrent"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = var.noncurrent_version_expiration_days
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# Presigned GETs work fine over the bucket's own TLS endpoint; still, deny any
# non-TLS access outright so nothing can ever read a photo in the clear.
data "aws_iam_policy_document" "photos" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.photos.arn, "${aws_s3_bucket.photos.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "photos" {
  bucket     = aws_s3_bucket.photos.id
  policy     = data.aws_iam_policy_document.photos.json
  depends_on = [aws_s3_bucket_public_access_block.photos]
}

# --- List Lambda ------------------------------------------------------------

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
  name               = "${var.name}-list"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
  tags               = var.tags
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.name}-list"
  retention_in_days = var.lambda_log_retention_days
  tags              = var.tags
}

# Read-only on exactly this bucket — enough to read the manifest and to presign
# GETs. No write, no other bucket.
data "aws_iam_policy_document" "lambda" {
  statement {
    sid       = "ReadPhotos"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:ListBucket"]
    resources = [aws_s3_bucket.photos.arn, "${aws_s3_bucket.photos.arn}/*"]
  }
  statement {
    sid       = "Logs"
    effect    = "Allow"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.lambda.arn}:*"]
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "${var.name}-list"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda.json
}

resource "aws_lambda_function" "list" {
  function_name    = "${var.name}-list"
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.12"
  handler          = "handler.handler"
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256
  timeout          = 15

  # The list endpoint mints a presigned URL for every photo's thumb AND full image
  # on each request — pure SigV4 crypto, so it's CPU-bound. Lambda CPU scales with
  # memory, and at the 128 MB default a full library (~1.4k photos = ~2.9k signings)
  # blew past the 15 s timeout. ~1.8 GB gives a full vCPU, dropping it to a few
  # seconds. The function only runs on page loads, so the cost is negligible.
  memory_size = var.list_lambda_memory_mb

  environment {
    variables = {
      PHOTO_BUCKET    = aws_s3_bucket.photos.id
      FAMILY_GROUP    = var.family_group
      URL_TTL_SECONDS = tostring(var.url_ttl_seconds)
      CORS_ORIGINS    = join(",", var.cors_origins)
    }
  }

  depends_on = [aws_iam_role_policy.lambda, aws_cloudwatch_log_group.lambda]
  tags       = var.tags
}

# --- HTTP API + Cognito JWT authorizer --------------------------------------

resource "aws_apigatewayv2_api" "this" {
  name          = var.name
  protocol_type = "HTTP"

  # Preflight is answered by API Gateway itself and does NOT hit the authorizer,
  # so the browser's OPTIONS never needs a token.
  cors_configuration {
    allow_origins = var.cors_origins
    allow_methods = ["GET", "OPTIONS"]
    allow_headers = ["authorization", "content-type"]
    max_age       = 3600
  }

  tags = var.tags
}

# The token is verified here — signature via the pool's JWKS, plus issuer and
# audience. Audience = the app client id, which only ID tokens carry, so this also
# quietly enforces "ID token, not access token".
resource "aws_apigatewayv2_authorizer" "cognito" {
  api_id           = aws_apigatewayv2_api.this.id
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  name             = "${var.name}-cognito"

  jwt_configuration {
    audience = [var.cognito_client_id]
    issuer   = var.cognito_issuer
  }
}

resource "aws_apigatewayv2_integration" "list" {
  api_id                 = aws_apigatewayv2_api.this.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.list.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "photos" {
  api_id             = aws_apigatewayv2_api.this.id
  route_key          = "GET /photos"
  target             = "integrations/${aws_apigatewayv2_integration.list.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.this.id
  name        = "$default"
  auto_deploy = true
  tags        = var.tags
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.list.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.this.execution_arn}/*/*"
}
