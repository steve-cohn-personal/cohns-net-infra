# Copy to org.auto.tfvars (gitignored, auto-loaded) and fill in real addresses.
#
# Each AWS account needs a globally-unique root email that you control and that
# actually delivers — it receives verification and account-recovery mail. Plus-
# addressing on a domain you own is the clean approach:
#
#   <you>+aws-shared@example.com
#
# Never commit the real values; they are the root identities of every account.

account_emails = {
  "shared-services" = "you+aws-shared@example.com"
  "dev"             = "you+aws-dev@example.com"
  "stage"           = "you+aws-stage@example.com"
  "prod"            = "you+aws-prod@example.com"
}
