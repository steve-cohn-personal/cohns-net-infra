# ---------------------------------------------------------------------------
# CI — GitHub OIDC roles for `terraform plan`/`apply` (see .github/workflows/
# terraform.yml).
#
# These roles live in the MANAGEMENT account, not the workload accounts, because
# Terraform state is here: state access is same-account, and the roles assume into
# the workload and shared-services accounts exactly like a local mgmt-admin run.
#
# Each role's own policy is deliberately tight — S3 access to its one environment's
# state, plus sts:AssumeRole to specific targets — so a compromised CI role holds
# no broad AWS power directly. The actual resource changes run under the assumed
# OrganizationAccountAccessRole; swapping that for a scoped TerraformExecution role
# is the next hardening step, and only the target side would change.
# ---------------------------------------------------------------------------

locals {
  state_bucket_arn = "arn:aws:s3:::cohns-tfstate-${aws_organizations_organization.this.master_account_id}"

  member_ids      = { for k, a in aws_organizations_account.member : k => a.id }
  org_access_role = { for k, id in local.member_ids : k => "arn:aws:iam::${id}:role/OrganizationAccountAccessRole" }

  # prod writes the apex DNS through the scoped Route53WriterFromProd role; dev and
  # stage write their NS delegation via the shared-services admin role for now.
  ci_assume_targets = {
    dev   = [local.org_access_role["dev"], local.org_access_role["shared-services"]]
    stage = [local.org_access_role["stage"], local.org_access_role["shared-services"]]
    prod  = [local.org_access_role["prod"], "arn:aws:iam::${local.member_ids["shared-services"]}:role/Route53WriterFromProd"]
  }
}

# One GitHub OIDC provider for the management account. Created directly (not via the
# module) so the three role modules can all reference it without a for_each cycle.
resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]

  tags = local.tags
}

data "aws_iam_policy_document" "tf_ci" {
  for_each = local.ci_assume_targets

  statement {
    sid       = "StateObjects"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${local.state_bucket_arn}/site/${each.key}/*"]
  }

  statement {
    sid       = "StateList"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [local.state_bucket_arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["site/${each.key}/*"]
    }
  }

  statement {
    sid       = "AssumeTargets"
    effect    = "Allow"
    actions   = ["sts:AssumeRole"]
    resources = each.value
  }
}

module "tf_ci" {
  source   = "../../modules/github-oidc"
  for_each = local.ci_assume_targets

  github_org     = var.github_org
  github_repo    = var.github_repo
  github_org_id  = var.github_org_id
  github_repo_id = var.github_repo_id

  role_name            = "gha-tf-${each.key}"
  allowed_environments = [each.key]

  create_oidc_provider = false
  oidc_provider_arn    = aws_iam_openid_connect_provider.github.arn

  create_inline_policy = true
  inline_policy_json   = data.aws_iam_policy_document.tf_ci[each.key].json

  tags = local.tags
}

output "tf_ci_role_arns" {
  description = "gha-tf-<env> role ARNs. Set as TF_PLAN_ROLE_ARN and TF_APPLY_ROLE_ARN per GitHub environment."
  value       = { for k, m in module.tf_ci : k => m.role_arn }
}
