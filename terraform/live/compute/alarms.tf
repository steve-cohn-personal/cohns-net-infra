# ---------------------------------------------------------------------------
# Paging for the comments API. These live in this stack, next to the ALB they watch,
# so they exist wherever the API does and need nothing else applied. (live/observability
# also defines ALB alarms behind enable_alb_alarms, but it has only ever been applied to
# dev, where compute is torn down — prod had no alarms at all. Leave that flag false for
# any environment that applies this file, or the alarm names collide.)
# ---------------------------------------------------------------------------

resource "aws_sns_topic" "alarms" {
  name = "comments-${var.environment}-alarms"
  # Deliberately NOT encrypted with alias/aws/sns like the topics above: CloudWatch
  # alarms cannot publish to a topic encrypted with the AWS-managed key (it needs a
  # customer-managed key whose policy allows cloudwatch.amazonaws.com), and the failure
  # is silent — the alarm fires and nothing arrives. The payload is an alarm name and a
  # number, so a $1/mo key buys nothing here.
  tags = local.tags
}

# Each address gets a confirmation email once; the subscription is inert until clicked.
resource "aws_sns_topic_subscription" "alarm_email" {
  for_each  = toset(var.alarm_emails)
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = each.value
}

# Server errors, from either side of the ALB.
#
#   HTTPCode_Target_5XX_Count  the app answered 5xx (the 2026-08-31 outage shape)
#   HTTPCode_ELB_5XX_Count     the ALB itself answered 502/503/504 (task down, timeout)
#
# The old alarm watched only the first, so a dead task paged nobody. Both metrics are
# absent, not zero, when nothing happened, hence FILL(). A count and not a rate on
# purpose: the site sees about 8 requests an hour, so a rate needs a traffic floor that
# would hide a real outage, while any 5xx at all is abnormal here. One hour, because a
# five-minute window usually contains no requests. Threshold 3 tolerates the one or two
# failures a visitor can hit while Aurora resumes from a pause.
resource "aws_cloudwatch_metric_alarm" "alb_5xx" {
  alarm_name          = "comments-${var.environment}-alb-5xx"
  alarm_description   = "3 or more 5xx responses in an hour, from the app (target) or the ALB. Check ECS task health and /readyz."
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 3
  evaluation_periods  = 1
  treat_missing_data  = "notBreaching"

  metric_query {
    id          = "errors"
    expression  = "FILL(target5xx, 0) + FILL(elb5xx, 0)"
    label       = "5xx responses"
    return_data = true
  }
  metric_query {
    id = "target5xx"
    metric {
      namespace   = "AWS/ApplicationELB"
      metric_name = "HTTPCode_Target_5XX_Count"
      period      = 3600
      stat        = "Sum"
      dimensions  = { LoadBalancer = module.service.alb_arn_suffix }
    }
  }
  metric_query {
    id = "elb5xx"
    metric {
      namespace   = "AWS/ApplicationELB"
      metric_name = "HTTPCode_ELB_5XX_Count"
      period      = 3600
      stat        = "Sum"
      dimensions  = { LoadBalancer = module.service.alb_arn_suffix }
    }
  }

  alarm_actions = [aws_sns_topic.alarms.arn]
  ok_actions    = [aws_sns_topic.alarms.arn]
  tags          = local.tags
}

# With /healthz as the ALB check this means "a task has stopped answering HTTP" — the
# process is wedged or crash-looping. It no longer says anything about the database.
resource "aws_cloudwatch_metric_alarm" "unhealthy_hosts" {
  alarm_name          = "comments-${var.environment}-unhealthy-hosts"
  alarm_description   = "A target has been failing the ALB health check for 5 minutes."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "UnHealthyHostCount"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  dimensions = {
    LoadBalancer = module.service.alb_arn_suffix
    TargetGroup  = module.service.target_group_arn_suffix
  }

  alarm_actions = [aws_sns_topic.alarms.arn]
  ok_actions    = [aws_sns_topic.alarms.arn]
  tags          = local.tags
}
