# ---------------------------------------------------------------------------
# CognitoUserAdminFromProd — lets the prod comments-api manage group membership
# (grant/revoke the family/moderators groups) so a moderator can approve people
# from the site instead of the AWS console.
#
# The pool lives here in shared-services; the API runs in prod. Rather than hand
# prod broad Cognito access, this role can ONLY list users and add/remove group
# membership on THIS pool, and is assumable ONLY by the prod comments task role.
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "cognito_user_admin_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type = "AWS"
      # The prod comments-api task role (live/compute prod). Referencing it by ARN
      # is fine before it exists — IAM stores the string.
      identifiers = ["arn:aws:iam::${var.prod_account_id}:role/comments-prod-task"]
    }
  }
}

data "aws_iam_policy_document" "cognito_user_admin" {
  statement {
    sid    = "ManageGroupMembership"
    effect = "Allow"
    actions = [
      "cognito-idp:ListUsers",
      "cognito-idp:ListUsersInGroup",
      "cognito-idp:AdminListGroupsForUser",
      "cognito-idp:AdminAddUserToGroup",
      "cognito-idp:AdminRemoveUserFromGroup",
    ]
    resources = [aws_cognito_user_pool.app.arn]
  }
}

resource "aws_iam_role" "cognito_user_admin_from_prod" {
  name               = "CognitoUserAdminFromProd"
  assume_role_policy = data.aws_iam_policy_document.cognito_user_admin_trust.json
  tags               = local.tags
}

resource "aws_iam_role_policy" "cognito_user_admin_from_prod" {
  name   = "cognito-user-admin"
  role   = aws_iam_role.cognito_user_admin_from_prod.id
  policy = data.aws_iam_policy_document.cognito_user_admin.json
}

output "cognito_user_admin_role_arn" {
  description = "Role the prod comments-api assumes to manage Cognito group membership."
  value       = aws_iam_role.cognito_user_admin_from_prod.arn
}
