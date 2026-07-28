# ---------------------------------------------------------------------------
# Container registry.
#
# ECR lives in shared-services — one registry the whole org pulls from, rather
# than a copy per account. CI (GitHub Actions) pushes via a scoped OIDC role; the
# workload accounts pull via a repository policy gated on the organization id.
# ---------------------------------------------------------------------------

resource "aws_ecr_repository" "comments_api" {
  name                 = "cohns/comments-api"
  image_tag_mutability = "MUTABLE" # sha + latest tags; flip to IMMUTABLE + digest pinning to harden

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = local.tags
}

# Keep the registry from growing without bound: drop untagged layers quickly and
# cap the number of retained images.
resource "aws_ecr_lifecycle_policy" "comments_api" {
  repository = aws_ecr_repository.comments_api.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images after 7 days"
        selection    = { tagStatus = "untagged", countType = "sinceImagePushed", countUnit = "days", countNumber = 7 }
        action       = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Keep only the most recent 20 images"
        selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 20 }
        action       = { type = "expire" }
      },
    ]
  })
}

# Any principal in the organization may pull. Push is not granted here — only the
# CI role below can push.
data "aws_iam_policy_document" "ecr_pull" {
  statement {
    sid    = "OrgPull"
    effect = "Allow"

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    actions = [
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
      "ecr:BatchCheckLayerAvailability",
    ]

    condition {
      test     = "StringEquals"
      variable = "aws:PrincipalOrgID"
      values   = [var.organization_id]
    }
  }
}

resource "aws_ecr_repository_policy" "comments_api" {
  repository = aws_ecr_repository.comments_api.name
  policy     = data.aws_iam_policy_document.ecr_pull.json
}

# --- CI push role -----------------------------------------------------------
# GitHub Actions builds on main and pushes here via OIDC. Scoped to pushing this
# one repository; GetAuthorizationToken is account-wide by necessity.
data "aws_iam_policy_document" "ecr_push" {
  statement {
    sid       = "Authenticate"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid    = "PushToCommentsApi"
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
      "ecr:PutImage",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
    ]
    resources = [aws_ecr_repository.comments_api.arn]
  }
}

module "ecr_push" {
  source = "../../modules/github-oidc"

  github_org     = var.github_org
  github_repo    = var.github_repo
  github_org_id  = var.github_org_id
  github_repo_id = var.github_repo_id

  role_name = "gha-ecr-push"

  # Push happens from main only; PR builds don't push, so they need no role.
  allowed_branches = ["main"]

  create_oidc_provider = true # the first (and only) OIDC provider in shared-services
  create_inline_policy = true
  inline_policy_json   = data.aws_iam_policy_document.ecr_push.json

  tags = local.tags
}

output "ecr_repository_url" {
  description = "The comments-api ECR repo URI (registry/name). Set as the ECR_REPOSITORY GitHub variable."
  value       = aws_ecr_repository.comments_api.repository_url
}

output "ecr_push_role_arn" {
  description = "The CI push role ARN. Set as the ECR_PUSH_ROLE_ARN GitHub variable."
  value       = module.ecr_push.role_arn
}
