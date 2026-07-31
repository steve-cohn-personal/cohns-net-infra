# ---------------------------------------------------------------------------
# Billing guardrails — this is the consolidated payer (management) account, so a
# budget here covers spend across every member account.
#
#   * A monthly COST budget with graduated email alerts (80% actual, 100% actual,
#     and forecast-to-exceed) — catches steady creep and end-of-month overruns.
#   * Cost Anomaly Detection — catches a spike a fixed threshold would miss: a
#     runaway resource can burn money while still "under budget" for the month.
#
# Budgets and Cost Explorer are global services (us-east-1 backed) and use the
# default provider fine. Anomaly detection needs Cost Explorer enabled on the
# account (it is) before it has data to analyze.
# ---------------------------------------------------------------------------

variable "billing_alert_emails" {
  description = "Addresses that receive budget + anomaly alerts."
  type        = list(string)
  default     = ["steve@cohns.net"]
}

variable "monthly_budget_usd" {
  description = "Monthly organization cost budget (USD). Alerts fire at 80%/100% actual and 100% forecast."
  type        = string
  default     = "50"
}

variable "anomaly_impact_usd" {
  description = "Only alert on cost anomalies whose total impact is at least this many USD (suppresses cent-level noise)."
  type        = string
  default     = "10"
}

resource "aws_budgets_budget" "monthly" {
  name         = "${var.name_prefix}-monthly-cost"
  budget_type  = "COST"
  limit_amount = var.monthly_budget_usd
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  # Early warning: actual spend past 80% of the budget.
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = var.billing_alert_emails
  }

  # Over budget: actual spend past 100%.
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = var.billing_alert_emails
  }

  # Trending over: forecast to exceed 100% by month end.
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = var.billing_alert_emails
  }
}

resource "aws_ce_anomaly_monitor" "services" {
  name              = "${var.name_prefix}-service-monitor"
  monitor_type      = "DIMENSIONAL"
  monitor_dimension = "SERVICE"
}

resource "aws_ce_anomaly_subscription" "alerts" {
  name             = "${var.name_prefix}-anomaly-alerts"
  frequency        = "DAILY"
  monitor_arn_list = [aws_ce_anomaly_monitor.services.arn]

  dynamic "subscriber" {
    for_each = var.billing_alert_emails
    content {
      type    = "EMAIL"
      address = subscriber.value
    }
  }

  # Digest an anomaly only once its cumulative impact clears the dollar floor, so
  # normal daily wiggle at this account's small scale doesn't page.
  threshold_expression {
    dimension {
      key           = "ANOMALY_TOTAL_IMPACT_ABSOLUTE"
      match_options = ["GREATER_THAN_OR_EQUAL"]
      values        = [var.anomaly_impact_usd]
    }
  }
}

output "monthly_budget_name" {
  description = "The organization monthly cost budget."
  value       = aws_budgets_budget.monthly.name
}
