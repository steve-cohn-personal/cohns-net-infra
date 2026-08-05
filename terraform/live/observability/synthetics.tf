# ---------------------------------------------------------------------------
# Synthetic monitoring: HTTP checks against the public site and API from a set of
# global probe locations. These are blackbox (no account access needed), so they
# cover prod www/steve and the dev API alike. Results land in the stack's hosted
# Prometheus as probe_success / probe_* series, which the SLO dashboard reads.
# ---------------------------------------------------------------------------

data "grafana_synthetic_monitoring_probes" "all" {}

locals {
  # Grafana's docs table shows human-readable locations ("North Virginia"); the API
  # returns the probe's own name field. Rather than guess at the mapping, resolve
  # defensively and let the precondition below print the authoritative list.
  probe_ids_by_name = data.grafana_synthetic_monitoring_probes.all.probes
  unknown_probes    = setsubtract(var.synthetic_probes, keys(local.probe_ids_by_name))
  selected_probe_ids = [
    for name in var.synthetic_probes : lookup(local.probe_ids_by_name, name, 0)
  ]
}

resource "grafana_synthetic_monitoring_check" "http" {
  for_each = { for t in local.synthetic_targets : t.job => t }

  job     = each.value.job
  target  = each.value.target
  enabled = true

  # Frequency and timeout are milliseconds.
  frequency = var.synthetic_frequency_seconds * 1000
  timeout   = 3000

  # An unknown name still fails loudly — but at plan time, and with the valid
  # names in the error, instead of a bare "key does not exist in map".
  probes = local.selected_probe_ids

  labels = {
    project = "cohns-net"
    env     = var.environment
  }

  lifecycle {
    precondition {
      condition = length(local.unknown_probes) == 0
      error_message = format(
        "Unknown synthetic_probes: %s. Valid probe names for this stack are: %s.",
        join(", ", local.unknown_probes),
        join(", ", sort(keys(local.probe_ids_by_name))),
      )
    }
  }

  settings {
    http {
      method             = "GET"
      ip_version         = "V4"
      valid_status_codes = [200]
      fail_if_not_ssl    = true
    }
  }
}
