variable "environment" {
  description = "dev | stage | prod."
  type        = string

  validation {
    condition     = contains(["dev", "stage", "prod"], var.environment)
    error_message = "environment must be dev, stage, or prod."
  }
}

variable "region" {
  description = "Region whose CloudWatch metrics and alarms this stack manages."
  type        = string
  default     = "us-west-2"
}

variable "account_role_arn" {
  description = "Role to assume into the workload account (dev owns the API/ALB/Aurora). Null = run in-account."
  type        = string
  default     = null
}

# --- Grafana Cloud -----------------------------------------------------------

variable "grafana_url" {
  description = "Grafana stack URL, e.g. https://<stack>.grafana.net. Not secret."
  type        = string
}

variable "grafana_auth" {
  description = "Grafana stack service-account token (Editor+). Supplied via TF_VAR_grafana_auth; never committed."
  type        = string
  sensitive   = true
}

variable "grafana_sm_url" {
  description = "Synthetic Monitoring API URL. The global endpoint routes for most stacks; if apply reports a region mismatch, use the regional URL from the error (e.g. https://synthetic-monitoring-api-us-west-0.grafana.net). Not secret."
  type        = string
  default     = "https://synthetic-monitoring-api.grafana.net"
}

variable "grafana_sm_access_token" {
  description = "Synthetic Monitoring access token. Supplied via TF_VAR_grafana_sm_access_token; never committed."
  type        = string
  sensitive   = true
}

variable "prometheus_datasource_uid" {
  description = "UID of the stack's hosted Prometheus, injected into the dashboard JSON at apply time. Grafana Cloud uses 'grafanacloud-prom' on every stack, so this is portable despite looking specific; list yours with GET /api/datasources."
  type        = string
  default     = "grafanacloud-prom"
}

# --- Synthetic monitoring ----------------------------------------------------

variable "synthetic_targets" {
  description = "Override for the probed endpoints. Null (default) uses the per-environment set in versions.tf (local.default_synthetic_targets)."
  type = list(object({
    job    = string
    target = string
  }))
  default = null
}

variable "synthetic_probes" {
  description = "Public probe locations to run each check from. Names must match the probe names the SM API returns; a bad name is caught at plan time by the precondition in synthetics.tf, which prints the valid set."
  type        = list(string)
  default     = ["NorthVirginia", "London", "Frankfurt", "Singapore", "SaoPaulo"]
}

variable "synthetic_frequency_seconds" {
  description = "How often each synthetic check runs. 60s keeps well inside the free tier for a handful of targets."
  type        = number
  default     = 60
}

# --- CloudWatch data source (Grafana Cloud assumes a role in this account) ----

# Grafana generates the external id and shows it, with its own AWS account id, in
# the CloudWatch data source's Settings tab — which means those values only exist
# once a data source does. That's a two-step handshake, so the CloudWatch half of
# this stack is gated:
#
#   Phase 1  enable_cloudwatch = false  — synthetics, dashboards, alarms, budget.
#            Everything that needs no handshake. Applies today.
#   Phase 2  enable_cloudwatch = true   — add the reader role + data source once
#            the account id / external id are known.
variable "enable_cloudwatch" {
  description = "Create the CloudWatch reader role, the Grafana data source, and the dashboards that query it. False until the Grafana account id / external id are known."
  type        = bool
  default     = false
}

variable "grafana_cloud_aws_account_id" {
  description = "The AWS account id Grafana Cloud assumes from, shown in the CloudWatch data source's Settings tab. Required when enable_cloudwatch is true."
  type        = string
  default     = null

  validation {
    condition     = var.grafana_cloud_aws_account_id == null || can(regex("^[0-9]{12}$", var.grafana_cloud_aws_account_id))
    error_message = "grafana_cloud_aws_account_id must be a 12-digit AWS account id."
  }
}

variable "grafana_cloud_external_id" {
  description = "External id tying the assume-role to your stack (same Settings tab). Guards against the confused-deputy problem. Required when enable_cloudwatch is true."
  type        = string
  default     = null
}

variable "cloudwatch_auth_type" {
  description = "CloudWatch data source authType. 'grafana_assume_role' is the Grafana Cloud managed handshake; 'arn' is the classic assume-role-by-ARN. Confirm which your stack's Settings tab offers before enabling."
  type        = string
  default     = "grafana_assume_role"

  validation {
    condition     = contains(["grafana_assume_role", "arn"], var.cloudwatch_auth_type)
    error_message = "cloudwatch_auth_type must be grafana_assume_role or arn."
  }
}

# --- Alerting ----------------------------------------------------------------

variable "alarm_emails" {
  description = "Addresses subscribed (via SNS) to infrastructure alarms. Each confirms once."
  type        = list(string)
  default     = ["steve@cohns.net"]
}

variable "enable_alb_alarms" {
  description = "Create ALB alarms by reading compute's remote state. True where the compute stack is applied (dev); false otherwise (stage/prod today)."
  type        = bool
  default     = true
}

variable "alb_5xx_threshold" {
  description = "Alarm when target 5xx responses over 5 minutes exceed this count."
  type        = number
  default     = 5
}

variable "alb_p95_latency_seconds" {
  description = "Alarm when ALB target p95 response time (over 5 minutes) exceeds this many seconds."
  type        = number
  default     = 2
}

variable "monthly_budget_usd" {
  description = "Monthly cost budget for this account. Alerts at 80% actual and 100% forecast."
  type        = number
  default     = 40
}

# --- Tag provenance ----------------------------------------------------------

variable "github_org" {
  description = "GitHub org, for the Repo tag."
  type        = string
  default     = "steve-cohn-personal"
}

variable "github_repo" {
  description = "GitHub repo, for the Repo tag."
  type        = string
  default     = "cohns-net-infra"
}
