# A folder to keep the cohns.net dashboards together in the stack.
resource "grafana_folder" "cohns" {
  title = "cohns.net"
}

# The CloudWatch data source, wired to assume the read-only role in this account.
# A fixed uid lets the committed dashboard JSON reference it without a lookup.
#
# Gated on enable_cloudwatch: Grafana mints the external id and shows it (with its
# own AWS account id) on this data source's Settings tab, so the trust policy in
# iam.tf can't be written until that handshake has happened once. See
# docs/observability.md.
resource "grafana_data_source" "cloudwatch" {
  count = var.enable_cloudwatch ? 1 : 0

  type = "cloudwatch"
  name = "cohns-cloudwatch-${var.environment}"
  uid  = "cohns-cw-${var.environment}"

  json_data_encoded = jsonencode({
    authType      = var.cloudwatch_auth_type
    defaultRegion = var.region
    assumeRoleArn = aws_iam_role.grafana_cloudwatch[0].arn
    externalId    = var.grafana_cloud_external_id
  })
}
