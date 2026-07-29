# ---------------------------------------------------------------------------
# Cognito — end-user identity for the site.
#
# This is the identity plane for site VISITORS (commenters, family photo viewers),
# separate from IAM Identity Center, which governs human access to the AWS console.
# The content API verifies these tokens via the pool's JWKS (RS256) instead of a
# shared HS256 secret; authorization is by group:
#   - moderators — may author recipes and moderate comments (cognito:groups claim)
#   - family     — invite-only access to the photo library (added by an admin)
#
# Self-signup is open (email-verified) so anyone can comment; the sensitive parts
# are gated on group membership, which only an admin grants.
# ---------------------------------------------------------------------------

resource "aws_cognito_user_pool" "app" {
  name = "cohns-net"

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  password_policy {
    minimum_length    = 12
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = true
  }

  # TOTP MFA available but not forced — reasonable for a personal site.
  mfa_configuration = "OPTIONAL"
  software_token_mfa_configuration {
    enabled = true
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  admin_create_user_config {
    allow_admin_create_user_only = false # self-signup allowed
  }

  # Cognito's built-in email (50/day) is fine here; move to SES for real volume.
  email_configuration {
    email_sending_account = "COGNITO_DEFAULT"
  }

  tags = local.tags
}

resource "aws_cognito_user_pool_client" "web" {
  name         = "cohns-net-web"
  user_pool_id = aws_cognito_user_pool.app.id

  # Public SPA client — no secret to leak in browser code.
  generate_secret = false

  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_ADMIN_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  supported_identity_providers         = ["COGNITO"]

  callback_urls = var.auth_callback_urls
  logout_urls   = var.auth_logout_urls

  access_token_validity  = 1
  id_token_validity      = 1
  refresh_token_validity = 30
  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }

  # Don't reveal whether an email is registered.
  prevent_user_existence_errors = "ENABLED"
}

resource "aws_cognito_user_group" "moderators" {
  name         = "moderators"
  user_pool_id = aws_cognito_user_pool.app.id
  description  = "May author recipes and moderate comments."
}

resource "aws_cognito_user_group" "family" {
  name         = "family"
  user_pool_id = aws_cognito_user_pool.app.id
  description  = "Invite-only access to the family photo library."
}

# --- Outputs for the content API's JWKS/RS256 config ------------------------

output "cognito_user_pool_id" {
  description = "The Cognito user pool id."
  value       = aws_cognito_user_pool.app.id
}

output "cognito_client_id" {
  description = "The web (SPA) app client id — the token audience."
  value       = aws_cognito_user_pool_client.web.id
}

output "cognito_issuer" {
  description = "Token issuer. Set the API's JWT issuer to this."
  value       = "https://cognito-idp.${var.region}.amazonaws.com/${aws_cognito_user_pool.app.id}"
}

output "cognito_jwks_url" {
  description = "JWKS endpoint. Set COMMENTS_JWKS_URL to this to verify Cognito tokens (RS256)."
  value       = "https://cognito-idp.${var.region}.amazonaws.com/${aws_cognito_user_pool.app.id}/.well-known/jwks.json"
}
