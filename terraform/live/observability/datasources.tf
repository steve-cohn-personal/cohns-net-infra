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

  # For grafana_assume_role (the Grafana Cloud managed handshake), Grafana injects
  # its own instance external id when it assumes the role — you supply only the
  # role ARN, not the external id. externalId in json_data is meaningful only for
  # the classic authType="arn" path, where Grafana assumes with its instance
  # credentials and you scope the trust yourself. So include it only there.
  json_data_encoded = jsonencode(merge(
    {
      authType      = var.cloudwatch_auth_type
      defaultRegion = var.region
      assumeRoleArn = aws_iam_role.grafana_cloudwatch[0].arn
    },
    var.cloudwatch_auth_type == "arn" ? { externalId = var.grafana_cloud_external_id } : {},
  ))
}
