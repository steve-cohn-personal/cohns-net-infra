# ---------------------------------------------------------------------------
# CloudTrail log archive.
#
# The locked S3 bucket that receives the organization trail's logs. The trail
# itself is defined in live/org (management account) — an org trail is a
# management-account resource — but its logs land here, in shared-services, away
# from the account that generates the most interesting events to tamper with.
#
# Apply order: this bucket must exist before live/org creates the trail (CloudTrail
# validates the bucket policy at trail-creation time). The two are coordinated by
# the deterministic bucket name below, not by shared state.
# ---------------------------------------------------------------------------

locals {
  cloudtrail_bucket_name = "cohns-cloudtrail-${var.shared_services_account_id}"
  cloudtrail_trail_arn   = "arn:aws:cloudtrail:${var.cloudtrail_home_region}:${var.management_account_id}:trail/${var.cloudtrail_name}"
}

resource "aws_s3_bucket" "cloudtrail" {
  bucket = local.cloudtrail_bucket_name

  # The audit trail is evidence. Losing it defeats the point of having it.
  lifecycle {
    prevent_destroy = true
  }

  tags = local.tags
}

resource "aws_s3_bucket_public_access_block" "cloudtrail" {
  bucket = aws_s3_bucket.cloudtrail.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "cloudtrail" {
  bucket = aws_s3_bucket.cloudtrail.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "cloudtrail" {
  bucket = aws_s3_bucket.cloudtrail.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

# Age logs into cheaper storage, then out. Audit logs are rarely read but must be
# retained; 400 days covers a year-plus of lookback without unbounded growth.
resource "aws_s3_bucket_lifecycle_configuration" "cloudtrail" {
  bucket = aws_s3_bucket.cloudtrail.id

  rule {
    id     = "archive-then-expire"
    status = "Enabled"

    filter {}

    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = 180
      storage_class = "GLACIER"
    }

    expiration {
      days = 400
    }

    noncurrent_version_expiration {
      noncurrent_days = 90
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  depends_on = [aws_s3_bucket_versioning.cloudtrail]
}

# The bucket policy CloudTrail requires, scoped to exactly our org trail via the
# aws:SourceArn condition — without it, any account's CloudTrail could write here.
data "aws_iam_policy_document" "cloudtrail" {
  statement {
    sid    = "AWSCloudTrailAclCheck"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }

    actions   = ["s3:GetBucketAcl"]
    resources = [aws_s3_bucket.cloudtrail.arn]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceArn"
      values   = [local.cloudtrail_trail_arn]
    }
  }

  statement {
    sid    = "AWSCloudTrailWrite"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }

    actions = ["s3:PutObject"]

    # The management account's own logs go under its account-id path; every member
    # account's logs go under the organization-id path.
    resources = [
      "${aws_s3_bucket.cloudtrail.arn}/AWSLogs/${var.management_account_id}/*",
      "${aws_s3_bucket.cloudtrail.arn}/AWSLogs/${var.organization_id}/*",
    ]

    condition {
      test     = "StringEquals"
      variable = "s3:x-amz-acl"
      values   = ["bucket-owner-full-control"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceArn"
      values   = [local.cloudtrail_trail_arn]
    }
  }

  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    actions = ["s3:*"]

    resources = [
      aws_s3_bucket.cloudtrail.arn,
      "${aws_s3_bucket.cloudtrail.arn}/*",
    ]

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "cloudtrail" {
  bucket = aws_s3_bucket.cloudtrail.id
  policy = data.aws_iam_policy_document.cloudtrail.json

  depends_on = [aws_s3_bucket_public_access_block.cloudtrail]
}

output "cloudtrail_bucket_name" {
  description = "The CloudTrail log-archive bucket. Feed this to live/org as cloudtrail_bucket_name."
  value       = aws_s3_bucket.cloudtrail.id
}
