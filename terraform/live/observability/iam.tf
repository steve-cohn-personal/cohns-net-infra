# ---------------------------------------------------------------------------
# The identity Grafana Cloud's hosted CloudWatch data source assumes to read this
# account's metrics. No access keys leave the account: Grafana authenticates from
# its own AWS account and assumes this role, gated by an external id — the same
# keyless, least-privilege pattern the rest of the repo uses for CI.
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "grafana_assume" {
  count = var.enable_cloudwatch ? 1 : 0

  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${var.grafana_cloud_aws_account_id}:root"]
    }

    # The external id ties this trust to our specific Grafana stack, closing the
    # confused-deputy hole a bare cross-account trust would leave open.
    condition {
      test     = "StringEquals"
      variable = "sts:ExternalId"
      values   = [var.grafana_cloud_external_id]
    }
  }
}

# Read-only: list/query metrics and alarms, resolve metric dimensions from tags,
# and read log groups for CloudWatch Logs panels. No mutating actions anywhere.
data "aws_iam_policy_document" "grafana_cloudwatch_read" {
  count = var.enable_cloudwatch ? 1 : 0

  statement {
    sid    = "CloudWatchMetricsRead"
    effect = "Allow"
    actions = [
      "cloudwatch:DescribeAlarmsForMetric",
      "cloudwatch:DescribeAlarmHistory",
      "cloudwatch:DescribeAlarms",
      "cloudwatch:ListMetrics",
      "cloudwatch:GetMetricData",
      "cloudwatch:GetMetricStatistics",
      "cloudwatch:GetInsightRuleReport",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "CloudWatchLogsRead"
    effect = "Allow"
    actions = [
      "logs:DescribeLogGroups",
      "logs:GetLogGroupFields",
      "logs:StartQuery",
      "logs:StopQuery",
      "logs:GetQueryResults",
      "logs:GetLogEvents",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "DimensionsFromTagsAndResources"
    effect = "Allow"
    actions = [
      "tag:GetResources",
      "ec2:DescribeTags",
      "ec2:DescribeInstances",
      "ec2:DescribeRegions",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role" "grafana_cloudwatch" {
  count = var.enable_cloudwatch ? 1 : 0

  name               = "grafana-cloudwatch-reader-${var.environment}"
  description        = "Assumed by Grafana Cloud to read CloudWatch metrics/logs. Read-only, external-id gated."
  assume_role_policy = data.aws_iam_policy_document.grafana_assume[0].json
  tags               = local.tags
}

resource "aws_iam_role_policy" "grafana_cloudwatch" {
  count = var.enable_cloudwatch ? 1 : 0

  name   = "cloudwatch-read"
  role   = aws_iam_role.grafana_cloudwatch[0].id
  policy = data.aws_iam_policy_document.grafana_cloudwatch_read[0].json
}
