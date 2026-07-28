# ---------------------------------------------------------------------------
# Bootstrap: the Terraform state backend.
#
# This is the one root module with a chicken-and-egg problem — Terraform needs a
# state bucket, and the state bucket is made by Terraform. It is applied once with
# local state, then `terraform init -migrate-state` moves its own state into the
# bucket it just created. From that point on nothing here is special.
#
# Run this with SSO admin credentials in the shared-services account.
# ---------------------------------------------------------------------------

locals {
  bucket_name = "${var.name_prefix}-tfstate-${data.aws_caller_identity.current.account_id}"
}

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "state" {
  bucket = local.bucket_name

  # State is the crown jewels. Losing it is worse than losing the infrastructure,
  # because the infrastructure survives and Terraform no longer knows about it.
  lifecycle {
    prevent_destroy = true
  }

  tags = var.tags
}

# Every apply writes a new version. This is the undo button for a corrupted or
# truncated state file, and it is not optional.
resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket = aws_s3_bucket.state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Reject any request that isn't TLS. S3 allows plaintext HTTP by default and the
# only way to turn that off is a bucket policy denial.
resource "aws_s3_bucket_policy" "state" {
  bucket = aws_s3_bucket.state.id
  policy = data.aws_iam_policy_document.state.json

  depends_on = [aws_s3_bucket_public_access_block.state]
}

data "aws_iam_policy_document" "state" {
  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    actions = ["s3:*"]

    resources = [
      aws_s3_bucket.state.arn,
      "${aws_s3_bucket.state.arn}/*",
    ]

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

# Keep noncurrent versions long enough to recover from a bad apply nobody noticed
# for a while, but not forever — state files are small but they add up.
resource "aws_s3_bucket_lifecycle_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    id     = "expire-noncurrent-state-versions"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 90
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  depends_on = [aws_s3_bucket_versioning.state]
}

# NOTE: there is deliberately no DynamoDB lock table here. Terraform 1.10+ locks
# state with a conditional-write lockfile in the bucket itself (`use_lockfile`),
# which removes a whole resource, its IAM policy, and its monthly cost.
