# ---------------------------------------------------------------------------
# Dashboards are committed JSON (exported from Grafana, versioned like code) and
# provisioned here. The datasource uid is injected at apply time via templatefile
# rather than written into the JSON, so the committed dashboard still carries no
# per-environment specifics.
#
# It is deliberately NOT a Grafana template variable: the SLO board is shared
# publicly, and public dashboards don't resolve template variables, so a
# datasource variable renders every panel as "Datasource was not found".
# ---------------------------------------------------------------------------

resource "grafana_dashboard" "slo" {
  folder = grafana_folder.cohns.uid
  config_json = templatefile("${path.module}/dashboards/slo.json", {
    prom = var.prometheus_datasource_uid
  })
}

# Aurora scale-to-zero cost. Follows the CloudWatch data source's gate — a panel
# with no data source behind it is worse than no panel — and, like the SLO board,
# takes its datasource uid injected at apply time (it is shared publicly, and
# public dashboards don't resolve template variables).
resource "grafana_dashboard" "aurora_cost" {
  count = var.enable_cloudwatch ? 1 : 0

  folder = grafana_folder.cohns.uid
  config_json = templatefile("${path.module}/dashboards/aurora-cost.json", {
    cw = grafana_data_source.cloudwatch[0].uid
    # Exact cluster id → plain MetricStat queries (not a SEARCH expression), which
    # the cost panel's metric-math requires. Convention is comments-<env>.
    db_cluster = "comments-${var.environment}"
  })
}

# Shared publicly so the site can link to it, like the SLO board. Exposes only the
# Aurora capacity/cost/connection series for this account — no account internals.
resource "grafana_dashboard_public" "aurora_cost" {
  count = var.enable_cloudwatch ? 1 : 0

  dashboard_uid = grafana_dashboard.aurora_cost[0].uid

  is_enabled             = true
  time_selection_enabled = true
  annotations_enabled    = false
  share                  = "public"
}

# ALB RED (rate/errors/duration) needs the ALB to exist. It is gated on BOTH the
# CloudWatch data source AND enable_alb_alarms (which tracks "compute is live") —
# with the compute stack torn down there is no ALB, and an empty RED board would
# read as an outage rather than a showcase. Re-applies automatically once compute
# is back and enable_alb_alarms flips to true.
resource "grafana_dashboard" "alb_red" {
  count = var.enable_cloudwatch && var.enable_alb_alarms ? 1 : 0

  folder      = grafana_folder.cohns.uid
  config_json = file("${path.module}/dashboards/alb-red.json")
}

# The SLO dashboard is the one embedded publicly on steve.cohns.net/observability.
# A public dashboard needs no login and exposes only the synthetic uptime/latency
# series — no account internals. Public-dashboard sharing must be enabled on the
# stack (Administration > Public dashboards) for this to apply.
resource "grafana_dashboard_public" "slo" {
  dashboard_uid = grafana_dashboard.slo.uid

  is_enabled             = true
  time_selection_enabled = true
  annotations_enabled    = false
  share                  = "public"
}
