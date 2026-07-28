# ---------------------------------------------------------------------------
# live/org — the Organization, its OUs, and the member accounts.
#
# The Organization itself is IMPORTED, not created (it has existed since 2019).
# Everything below the root — the OU structure and four fresh member accounts —
# is created here. The 2019 dev/prod accounts are suspended/closed and are left
# alone to age out; we do not reuse them.
#
# Apply with SSO admin credentials in the management account.
# ---------------------------------------------------------------------------

# Imported: `terraform import aws_organizations_organization.this o-ajlh1xjt64`.
#
# The two argument lists below MUST match the live org exactly, or a plan will try
# to REMOVE trusted access / policy types — which would break Identity Center.
# Current state (captured 2026-07-27): SCPs enabled; cloudtrail + sso trusted.
# Keep this in sync whenever a service gains org-wide trusted access.
resource "aws_organizations_organization" "this" {
  feature_set = "ALL"

  aws_service_access_principals = [
    "cloudtrail.amazonaws.com", # org-wide CloudTrail (roadmap)
    "sso.amazonaws.com",        # IAM Identity Center, already enabled
  ]

  enabled_policy_types = [
    "SERVICE_CONTROL_POLICY",
  ]
}

# ---------------------------------------------------------------------------
# Organizational units. The account is the blast radius; the OU is how policy
# (SCPs, later) is applied to a class of accounts at once.
# ---------------------------------------------------------------------------

resource "aws_organizations_organizational_unit" "infrastructure" {
  name      = "Infrastructure"
  parent_id = aws_organizations_organization.this.roots[0].id
}

resource "aws_organizations_organizational_unit" "workloads" {
  name      = "Workloads"
  parent_id = aws_organizations_organization.this.roots[0].id
}

# ---------------------------------------------------------------------------
# Member accounts. shared-services lives under Infrastructure; the three
# environments live under Workloads. Identical shape, created from one resource.
# ---------------------------------------------------------------------------

locals {
  ou_ids = {
    infrastructure = aws_organizations_organizational_unit.infrastructure.id
    workloads      = aws_organizations_organizational_unit.workloads.id
  }

  # short name => which OU it belongs in
  accounts = {
    "shared-services" = "infrastructure"
    "dev"             = "workloads"
    "stage"           = "workloads"
    "prod"            = "workloads"
  }
}

resource "aws_organizations_account" "member" {
  for_each = local.accounts

  name      = "${var.name_prefix}-${each.key}" # cohns-dev, cohns-prod, ...
  email     = var.account_emails[each.key]
  parent_id = local.ou_ids[each.value]

  # The role the management account assumes to administer a member account.
  # AWS creates it automatically in accounts made through Organizations.
  role_name = "OrganizationAccountAccessRole"

  # Let IAM principals in the account (i.e. SSO roles) view billing data.
  iam_user_access_to_billing = "ALLOW"

  # Removing an account from Terraform must NOT close it. Closing an AWS account
  # is a deliberate, 90-day, hard-to-reverse act — see the suspended 2019 accounts
  # still lingering in this very org. It is done by hand, never as plan fallout.
  close_on_deletion = false

  lifecycle {
    # Accounts are the one thing you never want a stray `terraform destroy` or an
    # attribute change to replace. email/name/role_name all force replacement.
    prevent_destroy = true
    ignore_changes  = [role_name]
  }

  tags = merge(local.tags, {
    Environment = each.key == "shared-services" ? "shared" : each.key
  })
}
