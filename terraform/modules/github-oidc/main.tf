# ---------------------------------------------------------------------------
# github-oidc: a deploy role that GitHub Actions can assume with no stored secret.
#
# GitHub mints a short-lived OIDC token per workflow run; AWS validates it against
# GitHub's provider and hands back temporary credentials. There is no access key
# to rotate, leak, or find in a public repo.
#
# The security of this hinges entirely on the `sub` condition below. A trust policy
# that omits it will happily accept a token from *anyone's* GitHub repository.
# ---------------------------------------------------------------------------

locals {
  github_oidc_url = "https://token.actions.githubusercontent.com"

  # Each entry becomes an allowed `sub` claim. Branch and environment scoping is
  # what stops a PR from a fork from assuming the production deploy role.
  allowed_subjects = concat(
    [for b in var.allowed_branches : "repo:${var.github_org}/${var.github_repo}:ref:refs/heads/${b}"],
    [for e in var.allowed_environments : "repo:${var.github_org}/${var.github_repo}:environment:${e}"],
    [for t in var.allowed_tag_patterns : "repo:${var.github_org}/${var.github_repo}:ref:refs/tags/${t}"],
  )
}

# One OIDC provider per account. Set create_oidc_provider = false and pass
# oidc_provider_arn if something else already made it.
resource "aws_iam_openid_connect_provider" "github" {
  count = var.create_oidc_provider ? 1 : 0

  url            = local.github_oidc_url
  client_id_list = ["sts.amazonaws.com"]

  # AWS stopped requiring an accurate thumbprint for this provider in 2023 — it
  # validates against its own trust store — but the field is still mandatory.
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]

  tags = var.tags
}

locals {
  provider_arn = var.create_oidc_provider ? aws_iam_openid_connect_provider.github[0].arn : var.oidc_provider_arn
}

data "aws_iam_policy_document" "trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # The line that matters. StringLike (not StringEquals) so tag patterns with
    # wildcards work; every subject is still anchored to this org and repo.
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = local.allowed_subjects
    }
  }
}

resource "aws_iam_role" "deploy" {
  name                 = var.role_name
  description          = "GitHub Actions deploy role for ${var.github_org}/${var.github_repo}"
  assume_role_policy   = data.aws_iam_policy_document.trust.json
  max_session_duration = var.max_session_duration

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "managed" {
  for_each = toset(var.managed_policy_arns)

  role       = aws_iam_role.deploy.name
  policy_arn = each.value
}

resource "aws_iam_role_policy" "inline" {
  count = var.create_inline_policy ? 1 : 0

  name   = "${var.role_name}-inline"
  role   = aws_iam_role.deploy.id
  policy = var.inline_policy_json
}
