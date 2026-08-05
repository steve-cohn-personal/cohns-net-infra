# ---------------------------------------------------------------------------
# Route53WriterFromProd — scoped cross-account DNS writer.
#
# prod needs to publish www.cohns.net and steve.cohns.net (and validate their ACM
# certs) into the apex zone, which lives here in shared-services. Rather than hand
# prod a role that owns the whole zone, this role can change ONLY those record sets
# and their validation records — enforced by the Route53 condition keys, not by
# hoping prod behaves.
#
# Trust is the prod account; tighten to prod's specific pipeline role once CI
# exists. Wiring: set prod's shared_services_role_arn (live/site) to this role's
# ARN when the prod apply runs as a prod identity (the CI/OIDC path). Under the
# current mgmt-admin bootstrap it still uses OrganizationAccountAccessRole, because
# a provider's assume_role starts from the ambient (mgmt) creds, which this role
# deliberately does not trust.
# ---------------------------------------------------------------------------

locals {
  # www.cohns.net, steve.cohns.net
  prod_record_names = [for label in var.prod_record_labels : "${label}.${var.domain_name}"]

  # Also the ACM validation records, which sit at _<hash>.<name>. The wildcard
  # covers them without opening up the rest of the zone.
  route53_writer_allowed_names = concat(
    local.prod_record_names,
    [for n in local.prod_record_names : "*.${n}"],
    # The apex itself (its A/AAAA alias records) and its ACM validation record
    # (_<hash>.cohns.net). The "_" prefix on the validation wildcard is deliberate:
    # a bare "*.cohns.net" would hand prod the entire first level of the zone
    # (api./dev./stage. delegations), which this role must never touch.
    [var.domain_name, "_*.${var.domain_name}"],
  )
}

data "aws_iam_policy_document" "route53_writer_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type = "AWS"
      identifiers = [
        # Prod's own identities (the target/CI-in-prod model).
        "arn:aws:iam::${var.prod_account_id}:root",
        # The management-account CI role that runs prod's terraform apply and needs
        # to write www/steve into the apex. Must already exist (live/org applied
        # first). Scoped to the same www/steve record set as any other assumer.
        "arn:aws:iam::${var.management_account_id}:role/gha-tf-prod",
      ]
    }
  }
}

data "aws_iam_policy_document" "route53_writer" {
  # checkov:skip=CKV_AWS_356:route53 GetChange/ListHostedZones take no resource-level ARN; the change action is scoped to www/steve by the record-name condition below.
  # Change only the prod-owned record sets. The condition is what makes this safe:
  # an attempt to touch any other name in the zone is denied by the policy, so the
  # blast radius is www/steve, not cohns.net.
  statement {
    sid       = "ChangeScopedRecords"
    effect    = "Allow"
    actions   = ["route53:ChangeResourceRecordSets"]
    resources = [aws_route53_zone.apex.arn]

    condition {
      test     = "StringLike"
      variable = "route53:ChangeResourceRecordSetsNormalizedRecordNames"
      values   = local.route53_writer_allowed_names
    }
  }

  # Reading the zone is needed for Terraform to plan and for record lookups.
  statement {
    sid    = "ReadZone"
    effect = "Allow"
    actions = [
      "route53:ListResourceRecordSets",
      "route53:GetHostedZone",
    ]
    resources = [aws_route53_zone.apex.arn]
  }

  # GetChange takes a change id, not a zone; it cannot be resource-scoped.
  statement {
    sid       = "PollChangeStatus"
    effect    = "Allow"
    actions   = ["route53:GetChange"]
    resources = ["*"]
  }
}

resource "aws_iam_role" "route53_writer_from_prod" {
  name                 = "Route53WriterFromProd"
  description          = "Assumable from prod; may change only ${join(", ", local.prod_record_names)} in the apex zone."
  assume_role_policy   = data.aws_iam_policy_document.route53_writer_trust.json
  max_session_duration = 3600

  tags = local.tags
}

resource "aws_iam_role_policy" "route53_writer_from_prod" {
  name   = "route53-writer-scoped"
  role   = aws_iam_role.route53_writer_from_prod.id
  policy = data.aws_iam_policy_document.route53_writer.json
}

output "route53_writer_role_arn" {
  description = "ARN of the scoped DNS writer. Set as prod's shared_services_role_arn once prod applies run as a prod identity."
  value       = aws_iam_role.route53_writer_from_prod.arn
}
