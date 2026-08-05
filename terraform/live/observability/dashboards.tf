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

# These two query CloudWatch, so they follow the data source's gate — a dashboard
# with no data source behind it is worse than no dashboard.
resource "grafana_dashboard" "aurora_cost" {
  count = var.enable_cloudwatch ? 1 : 0

  folder      = grafana_folder.cohns.uid
  config_json = file("${path.module}/dashboards/aurora-cost.json")
}

resource "grafana_dashboard" "alb_red" {
  count = var.enable_cloudwatch ? 1 : 0

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
