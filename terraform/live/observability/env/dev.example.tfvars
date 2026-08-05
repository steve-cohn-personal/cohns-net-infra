# Copy to dev.tfvars (gitignored) and fill in real values.
#
# Requires: live/site (prod) applied for www/steve to probe, live/compute (dev)
# applied for the API + ALB alarms, and a free Grafana Cloud stack with Synthetic
# Monitoring enabled.
#
# The two SECRET tokens are NOT set here. Export them into the environment before
# apply so they never touch a file:
#   export TF_VAR_grafana_auth=<stack service-account token>
#   export TF_VAR_grafana_sm_access_token=<synthetic monitoring token>

environment = "dev"
region      = "us-west-2"

account_role_arn = "arn:aws:iam::<dev-account-id>:role/OrganizationAccountAccessRole"

# --- Grafana Cloud (non-secret bits) ---
grafana_url    = "https://<your-stack>.grafana.net"
grafana_sm_url = "https://synthetic-monitoring-api-<region>.grafana.net"

# Connections > Data sources > grafanacloud-<stack>-prom : the uid in the URL.
grafana_prometheus_ds_uid = "grafanacloud-<stack>-prom"

# Both shown on the hosted CloudWatch data source's "IAM role" setup screen in
# your stack — copy them from there, don't guess.
grafana_cloud_aws_account_id = "<grafana-cloud-aws-account-id>"
grafana_cloud_external_id    = "<external-id-shown-on-that-screen>"

# --- Synthetics ---
# Probe from a handful of global locations. Names must match Grafana's public
# probe list (Synthetic Monitoring > Config > Probes).
synthetic_probes = ["NorthVirginia", "London", "Frankfurt", "Singapore", "SaoPaulo"]

# --- Alerting ---
alarm_emails       = ["steve@cohns.net"]
enable_alb_alarms  = true
monthly_budget_usd = 40
