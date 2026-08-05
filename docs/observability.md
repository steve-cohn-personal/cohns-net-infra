# Observability

**The goal: the site watches itself, and every part of the watching is code.** No dashboard was
built by clicking. No agent runs on a box. No access key was issued to a vendor. The whole
observability layer is one Terraform root module — `terraform/live/observability` — and it costs
nothing per month.

Live page: [steve.cohns.net/observability](https://steve.cohns.net/observability/).

## What gets watched

| Signal | Source | Why this source |
| --- | --- | --- |
| Uptime + latency, worldwide | Grafana Synthetic Monitoring | Blackbox — proves the *user's* experience, not the server's opinion of itself |
| Request rate, 5xx, p50/p95/p99 | ALB metrics via CloudWatch | RED at the edge, with **no agent and no extra compute** |
| Aurora capacity (ACU) + connections | RDS metrics via CloudWatch | The scale-to-zero story, and cost as a live number |
| Target health | ALB target group | Catches a task that's up but not serving |
| App-level RED | `/metrics` on the comments API | Prometheus histograms, labelled by handler — additive, not load-bearing |

## Decisions

### Grafana Cloud free tier, not self-hosted Prometheus

Self-hosting Prometheus + Grafana would demonstrate that I can run the stack — and I have, for
years. But on this project it costs ~$25–30/mo of always-on Fargate to watch a site that itself
costs less than that, and it comes with no global probe network. The free tier gives 10k series,
14-day retention, and synthetic probes from real locations on five continents for **$0**. The
same reasoning that put the app on Fargate instead of EKS applies here: pick the option whose
bill matches the workload, and say why.

The roadmap called this "Prometheus + Grafana, **or a managed equivalent**." This is the managed
equivalent, and the exporters/dashboards are portable if that changes.

### CloudWatch by role-assumption, not an access key

The obvious way to let a SaaS vendor read your metrics is to mint an IAM user and paste its key
into their UI. That's a long-lived credential in a third party's database — exactly what the rest
of [access-strategy.md](access-strategy.md) exists to avoid.

Instead `iam.tf` creates a role that trusts Grafana's own AWS account, gated by an **external id**
so it can't be used as a confused deputy, with a read-only policy (metrics, logs, and tag lookups
— no mutating action anywhere). Grafana assumes it and gets short-lived credentials. There is no
key to leak or rotate. Same pattern as CI's GitHub OIDC federation.

### Metrics from the load balancer, not from an agent

An agent per task is the reflex, and it's the wrong reflex for a one-service platform: it costs
memory in every task, needs its own config and upgrades, and produces a second thing that can
break. The ALB already emits request count, error codes, and response-time percentiles to
CloudWatch for free. That is a complete RED signal without running anything.

The app *does* expose Prometheus metrics at `/metrics` (see `services/comments-api/app/main.py`),
because handler-level latency is genuinely better than edge-level latency when you're debugging.
But nothing on the dashboards depends on it — scrape it when it earns its keep.

### Alerting stays on AWS, not in Grafana

Grafana draws the pictures; **CloudWatch alarms into SNS do the paging.** If the alerting path
runs through the same vendor as the dashboards, a vendor outage takes out both your visibility
and your ability to find out you lost it. Alarms live in the account and region where the metrics
are, so they keep firing regardless.

Three alarms today — 5xx count, p95 latency, unhealthy targets — plus the one that actually
matters on a personal project: a **monthly cost budget** at 80% actual / 100% forecast. The
realistic failure mode here isn't an outage, it's a runaway bill.

### Dashboards are committed JSON

Dashboards live in `dashboards/*.json` and are provisioned by `grafana_dashboard`. They reference
their data sources through templating variables rather than hardcoded UIDs, and use wildcard
CloudWatch dimensions rather than baked-in ARNs, so the same JSON works in any environment. Edit
in the UI to explore; commit the export to keep it.

## Layout

```
terraform/live/observability/
  versions.tf      Providers: aws (+us-east-1 for Budgets), grafana. Tokens come from
                   the environment at apply time — never a tfvars, never CI.
  iam.tf           The read-only role Grafana Cloud assumes (external-id gated).
  datasources.tf   Folder + CloudWatch data source wired to that role.
  synthetics.tf    HTTP checks per endpoint, from a configurable probe list.
  dashboards.tf    Provisions the JSON; publishes the SLO board publicly.
  alerts.tf        SNS topic, ALB alarms, monthly cost budget.
  dashboards/      slo.json · aurora-cost.json · alb-red.json
```

## Applying it

This stack is **applied manually**, like `live/data` and `live/compute` — CI's `terraform.yml`
manages `live/site` only. See [promotion.md](promotion.md).

The two Grafana tokens are secrets and are passed through the environment, so they never touch a
file that could be committed:

```sh
export TF_VAR_grafana_auth='<stack service-account token>'
export TF_VAR_grafana_sm_access_token='<synthetic monitoring token>'

cd terraform/live/observability
terraform init -reconfigure -backend-config=env/dev.backend.hcl
terraform apply -var-file=env/dev.tfvars
```

Then take the `slo_public_url` output and paste it into `PUBLIC_DASHBOARD_URL` in
`site/js/observability.js`. Until it's set, the page renders a "pending apply" placeholder rather
than a dead frame. Publishing to prod is a content sync (`site-deploy.yml`, `environment=prod`);
no `live/site` apply is needed because the page carries no CSP change (see below).

### The dashboard is linked, not embedded — Grafana Cloud can't be iframed

We tried the obvious thing first: embed the public dashboard in an `<iframe>` and widen the site
CSP with `frame-src https://*.grafana.net`. It doesn't work. Grafana Cloud serves the public
dashboard with `X-Frame-Options: deny` and CSP `frame-ancestors 'none'`, and that is **not
configurable on Cloud** — `allow_embedding` is a self-hosted `grafana.ini` setting, there is no
Embed tab in the share modal, and Grafana support confirms modifying `X-Frame-Options` is
unsupported for anti-clickjacking reasons. The framed resource declines regardless of what our
CSP permits.

So `site/js/observability.js` renders a preview card that **links out** to the dashboard in a new
tab, and `live/site` carries **no** `frame-src` (a dormant directive a review would flag). If
Grafana ever ships a tenant `frame-ancestors` allowlist, swapping back is small: re-add `frame-src`
to the CSP and inject an `<iframe>` instead of the preview card. Loading the dashboard URL directly
works perfectly — only framing is blocked — so don't read a good direct load as a working embed.

### Panels are pinned to a datasource uid, not a template variable

`dashboards.tf` injects the Prometheus uid into `slo.json` with `templatefile`. That is not
incidental: **public dashboards do not resolve Grafana template variables**, so a `datasource`
variable renders every panel as "Datasource was not found" on the public URL while looking perfect
to a logged-in viewer. Injecting at apply time keeps the committed JSON environment-agnostic
without relying on a variable that the public renderer ignores.

### The stack token needs Admin

The service account behind `TF_VAR_grafana_auth` must be **Admin** on the stack. A Viewer fails at
`grafana_folder` with `403 folders:create`, and Editor gets past the folder only to stumble on the
public dashboard. Change the role in **Administration → Users and access → Service accounts**; the
existing token keeps working, since the role belongs to the account and not to the token.

### `403 "tenant is disabled"` means wrong region, not a broken tenant

SM runs as its own tenant, and it is **regional**. The global endpoint
`synthetic-monitoring-api.grafana.net` answers `403 "tenant is disabled"` for a tenant that lives
elsewhere — which reads like an uninitialized tenant and sends you into the UI to fix something
that isn't broken. This stack's tenant is in `us-west-0`, so `grafana_sm_url` is set explicitly in
`env/dev.tfvars`.

To find the right host, ask each region for the probe list and look for the 200 — a wrong-region
tenant gives 403, a region that doesn't exist gives 530:

```sh
for h in us-east-0 us-west-0 us-central-0 eu-west-0 eu-west-2 au-southeast-0; do
  printf '%-16s ' "$h"
  curl -s --connect-timeout 5 -o /dev/null -w '%{http_code}\n' \
    -H "Authorization: Bearer $TF_VAR_grafana_sm_access_token" \
    "https://synthetic-monitoring-api-$h.grafana.net/api/v1/probe/list"
done
```

The tenant still has to be initialized once in the stack UI, which also mints the SM access token.

This is a bootstrap step of the same kind as `bootstrap/` — a chicken-and-egg that has to happen
outside the code that depends on it. It could be codified with
`grafana_synthetic_monitoring_installation`, but that needs an org-level Cloud Access Policy
token on top of the two stack tokens; not worth the extra credential for a once-per-stack action.

### Two phases, because the CloudWatch trust is a handshake

Grafana mints the external id and displays it — with its own AWS account id — on the CloudWatch
data source's **Settings** tab. The IAM trust policy in `iam.tf` needs both. So the values only
exist *after* a data source does, and no single apply can close that loop. Rather than pretend
otherwise, the CloudWatch half is gated behind `enable_cloudwatch`:

**Phase 1** (`enable_cloudwatch = false`) — synthetic checks, the SLO dashboard, the public
dashboard, SNS alarms, and the cost budget. Everything that needs no handshake.

**Phase 2** (`enable_cloudwatch = true`) — add `grafana_cloud_aws_account_id` and
`grafana_cloud_external_id` from that Settings tab, then apply again to create the reader role,
the data source, and the two dashboards that query it (Aurora cost, ALB RED).

Confirm which auth provider your stack offers before phase 2 and set `cloudwatch_auth_type`
accordingly — `grafana_assume_role` is Grafana Cloud's managed handshake; `arn` is the classic
assume-role-by-ARN.

Public-dashboard sharing may also need enabling once on the stack (Administration → Public
dashboards); on current Grafana Cloud it is often on by default.

## What's deliberately not here

- **Tracing.** One service and one database; traces would be ceremony. The moment a second
  service calls the first, OpenTelemetry earns its place.
- **Log aggregation.** ECS already ships task logs to CloudWatch Logs, and the data source can
  query them. Shipping them off-account is a cost decision that light traffic doesn't justify.
- **An SLO burn-rate alert.** The dashboard shows availability against a target; multi-window
  burn-rate alerting is the right next step once there's enough traffic for the math to mean
  something.
