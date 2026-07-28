# ---------------------------------------------------------------------------
# IAM Identity Center — permission sets and account assignments.
#
# The instance, the `Administrators` group, and the `steve.cohn` user were created
# by hand during bootstrap (root, before any Terraform existed). They are read here
# as data sources, not managed. The permission sets and every account assignment
# ARE managed here — including the AdministratorAccess set, which is imported.
#
# Solo-operator model: every permission set is assigned to the single
# `Administrators` group. That gives the one human a menu of roles per account and
# lets him "live in ReadOnly and step up deliberately". Split into tiered groups
# once there is more than one person.
#
# All resources below use the us-east-1 `aws.identity` provider — Identity Center's
# home region.
# ---------------------------------------------------------------------------

data "aws_ssoadmin_instances" "this" {
  provider = aws.identity
}

locals {
  sso_instance_arn  = tolist(data.aws_ssoadmin_instances.this.arns)[0]
  identity_store_id = tolist(data.aws_ssoadmin_instances.this.identity_store_ids)[0]
}

data "aws_identitystore_group" "administrators" {
  provider          = aws.identity
  identity_store_id = local.identity_store_id

  alternate_identifier {
    unique_attribute {
      attribute_path  = "DisplayName"
      attribute_value = "Administrators"
    }
  }
}

locals {
  # Short name => account id, for every account we assign into.
  assignable_account_ids = merge(
    { management = aws_organizations_organization.this.master_account_id },
    { for k, a in aws_organizations_account.member : k => a.id },
  )

  # Permission sets: AWS-managed policy + session length. Uniform 8h — for a solo
  # operator the security boundary is the least-privilege split and MFA, not the
  # session length. Tighten per-set here if that changes.
  permission_sets = {
    AdministratorAccess = {
      description      = "Full access. Break-glass and org administration."
      managed_policy   = "arn:aws:iam::aws:policy/AdministratorAccess"
      session_duration = "PT8H"
    }
    PowerUserAccess = {
      description      = "Everything except IAM and Organizations. Day-to-day build work."
      managed_policy   = "arn:aws:iam::aws:policy/PowerUserAccess"
      session_duration = "PT8H"
    }
    ReadOnlyAccess = {
      description      = "Read-only. The default posture; investigate without risk."
      managed_policy   = "arn:aws:iam::aws:policy/ReadOnlyAccess"
      session_duration = "PT8H"
    }
    Billing = {
      description      = "Billing console and Cost Explorer."
      managed_policy   = "arn:aws:iam::aws:policy/job-function/Billing"
      session_duration = "PT8H"
    }
  }

  # Which permission set is offered in which accounts. ReadOnly everywhere; admin
  # on management (org administration) and dev (disposable sandbox); PowerUser on
  # the accounts where real infra gets built; Billing on management only.
  assignment_matrix = {
    AdministratorAccess = ["management", "dev"]
    PowerUserAccess     = ["shared-services", "stage", "prod"]
    ReadOnlyAccess      = ["management", "shared-services", "dev", "stage", "prod"]
    Billing             = ["management"]
  }

  # Flatten the matrix to "<ps>:<account>" => {ps, account} for for_each.
  assignments = merge([
    for ps, accts in local.assignment_matrix : {
      for acct in accts : "${ps}:${acct}" => { ps = ps, account = acct }
    }
  ]...)
}

resource "aws_ssoadmin_permission_set" "this" {
  provider = aws.identity
  for_each = local.permission_sets

  name             = each.key
  description      = each.value.description
  instance_arn     = local.sso_instance_arn
  session_duration = each.value.session_duration
}

resource "aws_ssoadmin_managed_policy_attachment" "this" {
  provider = aws.identity
  for_each = local.permission_sets

  instance_arn       = local.sso_instance_arn
  permission_set_arn = aws_ssoadmin_permission_set.this[each.key].arn
  managed_policy_arn = each.value.managed_policy
}

resource "aws_ssoadmin_account_assignment" "this" {
  provider = aws.identity
  for_each = local.assignments

  instance_arn       = local.sso_instance_arn
  permission_set_arn = aws_ssoadmin_permission_set.this[each.value.ps].arn

  principal_id   = data.aws_identitystore_group.administrators.group_id
  principal_type = "GROUP"

  target_id   = local.assignable_account_ids[each.value.account]
  target_type = "AWS_ACCOUNT"
}
