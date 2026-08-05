# ---------------------------------------------------------------------------
# Alerting. Grafana draws the pictures; AWS-native alarms do the paging, exactly
# as the roadmap frames Phase 4 ("CloudWatch alarms -> SNS -> phone; Budget alerts
# per account"). Alarms live in the account/region where the metrics are, so they
# keep working even if Grafana is down — you don't want your paging path to depend
# on your dashboard vendor.
# ---------------------------------------------------------------------------

resource "aws_sns_topic" "alarms" {
  name = "observability-${var.environment}-alarms"
  # SSE with the AWS-managed SNS key — encryption at rest, no key to manage or pay for.
  kms_master_key_id = "alias/aws/sns"
  tags              = local.tags
}

# Email subscriptions require a one-time confirmation click per address. Add an
# SMS or a chatbot subscription here for the "-> phone" half of the roadmap line.
resource "aws_sns_topic_subscription" "alarm_email" {
  for_each  = toset(var.alarm_emails)
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = each.value
}

# --- ALB alarms (only where the compute stack is applied) --------------------

# Read the ALB identifiers from compute's remote state. When compute isn't applied
# for this environment (stage/prod today), set enable_alb_alarms = false and these
# are skipped; the budget alarm below still applies.
data "terraform_remote_state" "compute" {
  count   = var.enable_alb_alarms ? 1 : 0
  backend = "s3"
  config = {
    bucket = "cohns-tfstate-562995958167"
    key    = "compute/${var.environment}/terraform.tfstate"
    region = "us-west-2"
  }
}

locals {
  alb_suffix = var.enable_alb_alarms ? data.terraform_remote_state.compute[0].outputs.alb_arn_suffix : null
  tg_suffix  = var.enable_alb_alarms ? data.terraform_remote_state.compute[0].outputs.target_group_arn_suffix : null
}

resource "aws_cloudwatch_metric_alarm" "alb_5xx" {
  count = var.enable_alb_alarms ? 1 : 0

  alarm_name          = "comments-${var.environment}-alb-5xx"
  alarm_description   = "Target 5xx responses over 5 minutes exceeded the threshold."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_Target_5XX_Count"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.alb_5xx_threshold
  treat_missing_data  = "notBreaching"
  dimensions          = { LoadBalancer = local.alb_suffix }

  alarm_actions = [aws_sns_topic.alarms.arn]
  ok_actions    = [aws_sns_topic.alarms.arn]
  tags          = local.tags
}

resource "aws_cloudwatch_metric_alarm" "alb_latency" {
  count = var.enable_alb_alarms ? 1 : 0

  alarm_name          = "comments-${var.environment}-alb-p95-latency"
  alarm_description   = "ALB target p95 response time over 5 minutes exceeded the threshold."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "TargetResponseTime"
  extended_statistic  = "p95"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.alb_p95_latency_seconds
  treat_missing_data  = "notBreaching"
  dimensions          = { LoadBalancer = local.alb_suffix }

  alarm_actions = [aws_sns_topic.alarms.arn]
  ok_actions    = [aws_sns_topic.alarms.arn]
  tags          = local.tags
}

resource "aws_cloudwatch_metric_alarm" "alb_unhealthy_hosts" {
  count = var.enable_alb_alarms ? 1 : 0

  alarm_name          = "comments-${var.environment}-unhealthy-hosts"
  alarm_description   = "One or more targets have been unhealthy for 5 minutes."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "UnHealthyHostCount"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  dimensions          = { LoadBalancer = local.alb_suffix, TargetGroup = local.tg_suffix }

  alarm_actions = [aws_sns_topic.alarms.arn]
  ok_actions    = [aws_sns_topic.alarms.arn]
  tags          = local.tags
}

# --- Cost budget -------------------------------------------------------------

# The realistic risk on a personal project isn't an outage, it's a runaway bill.
# One monthly budget per account, alerting at 80% actual and 100% forecast.
resource "aws_budgets_budget" "monthly" {
  provider = aws.us_east_1

  name         = "monthly-cost-${var.environment}"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = var.alarm_emails
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = var.alarm_emails
  }
}
