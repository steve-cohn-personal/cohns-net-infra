# ---------------------------------------------------------------------------
# Service Control Policies — the guardrails.
#
# These are DENY policies layered on top of the default FullAWSAccess SCP: they
# subtract a few dangerous powers and leave everything else alone. Deny always
# wins, so this is the safe shape — there is no allow-list to accidentally choke.
#
# Attached to the Infrastructure and Workloads OUs, never the root. SCPs do not
# apply to the management account at all (AWS exempts it), so administering the org
# from here is never at risk from anything below.
# ---------------------------------------------------------------------------

locals {
  # Every action still works in these two regions. Everything global is exempted
  # by NotAction below rather than by region.
  allowed_regions = ["us-east-1", "us-west-2"]

  # SCPs go on the OUs that hold member accounts.
  scp_target_ou_ids = [
    aws_organizations_organizational_unit.infrastructure.id,
    aws_organizations_organizational_unit.workloads.id,
  ]
}

# --- Guardrail 1: protect org membership and the audit trail --------------------

data "aws_iam_policy_document" "protect_foundation" {
  statement {
    sid       = "DenyLeavingOrganization"
    effect    = "Deny"
    actions   = ["organizations:LeaveOrganization"]
    resources = ["*"]
  }

  statement {
    sid    = "ProtectCloudTrail"
    effect = "Deny"
    actions = [
      "cloudtrail:StopLogging",
      "cloudtrail:DeleteTrail",
      "cloudtrail:UpdateTrail",
      "cloudtrail:PutEventSelectors",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "ProtectConfig"
    effect = "Deny"
    actions = [
      "config:StopConfigurationRecorder",
      "config:DeleteConfigurationRecorder",
      "config:DeleteDeliveryChannel",
    ]
    resources = ["*"]
  }
}

resource "aws_organizations_policy" "protect_foundation" {
  name        = "guardrail-protect-foundation"
  description = "Deny leaving the org and disabling CloudTrail/Config."
  type        = "SERVICE_CONTROL_POLICY"
  content     = data.aws_iam_policy_document.protect_foundation.json
}

# --- Guardrail 2: no root-user activity in member accounts ----------------------

data "aws_iam_policy_document" "deny_root" {
  statement {
    sid       = "DenyRootUser"
    effect    = "Deny"
    actions   = ["*"]
    resources = ["*"]

    # Only the literal account root matches. SSO roles and the
    # OrganizationAccountAccessRole are unaffected — their principal is a role,
    # not `...:root`. Lift this from the management account if a genuine root-only
    # task ever comes up in a member account.
    condition {
      test     = "StringLike"
      variable = "aws:PrincipalArn"
      values   = ["arn:aws:iam::*:root"]
    }
  }
}

resource "aws_organizations_policy" "deny_root" {
  name        = "guardrail-deny-root"
  description = "Deny all actions by the account root user in member accounts."
  type        = "SERVICE_CONTROL_POLICY"
  content     = data.aws_iam_policy_document.deny_root.json
}

# --- Guardrail 3: confine activity to approved regions --------------------------

data "aws_iam_policy_document" "region_lock" {
  statement {
    sid       = "DenyOutsideAllowedRegions"
    effect    = "Deny"
    resources = ["*"]

    # Global (or us-east-1-anchored) services must keep working regardless of the
    # requested region. sts:* is the important one — cross-account role assumption
    # must not be region-locked, or Terraform can't reach the member accounts.
    not_actions = [
      "iam:*",
      "sts:*",
      "organizations:*",
      "account:*",
      "route53:*",
      "route53domains:*",
      "cloudfront:*",
      "waf:*",
      "wafv2:*",
      "shield:*",
      "globalaccelerator:*",
      "support:*",
      "trustedadvisor:*",
      "health:*",
      "budgets:*",
      "ce:*",
      "cur:*",
      "artifact:*",
      "tax:*",
    ]

    condition {
      test     = "StringNotEquals"
      variable = "aws:RequestedRegion"
      values   = local.allowed_regions
    }
  }
}

resource "aws_organizations_policy" "region_lock" {
  name        = "guardrail-region-lock"
  description = "Deny actions outside us-east-1/us-west-2, except global services."
  type        = "SERVICE_CONTROL_POLICY"
  content     = data.aws_iam_policy_document.region_lock.json
}

# --- Attach all three to both member-account OUs --------------------------------

resource "aws_organizations_policy_attachment" "protect_foundation" {
  for_each  = toset(local.scp_target_ou_ids)
  policy_id = aws_organizations_policy.protect_foundation.id
  target_id = each.value
}

resource "aws_organizations_policy_attachment" "deny_root" {
  for_each  = toset(local.scp_target_ou_ids)
  policy_id = aws_organizations_policy.deny_root.id
  target_id = each.value
}

resource "aws_organizations_policy_attachment" "region_lock" {
  for_each  = toset(local.scp_target_ou_ids)
  policy_id = aws_organizations_policy.region_lock.id
  target_id = each.value
}
