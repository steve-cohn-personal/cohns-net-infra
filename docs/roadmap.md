# Roadmap

## Phase 1 — Foundation ✅ complete

An access strategy, an account layout with a promotion path, a public repo with no credentials,
and live sites.

- [x] Repository scaffolding, `.gitignore` hardened for a public repo
- [x] `bootstrap/` — versioned, encrypted, TLS-only state backend with native S3 locking
- [x] `modules/static-site` — S3 + OAC + CloudFront + ACM + Route53, strict CSP
- [x] `modules/github-oidc` — keyless CI, scoped by repo/branch/environment (immutable subjects)
- [x] `live/site` — one root module, three environments
- [x] `live/org` — Organization (imported), Infrastructure/Workloads OUs, four member accounts
- [x] IAM Identity Center permission sets and assignments; root retired (no access keys)
- [x] SCP guardrails (deny leave-org / protect CloudTrail+Config / deny root / region-lock)
- [x] Org-wide CloudTrail to a locked archive in shared-services
- [x] `live/shared-services` — apex hosted zone, Google Workspace email (SPF/DKIM/DMARC),
      delegated subzones, `Route53WriterFromProd`, ECR
- [x] CI: fmt / validate / per-environment plan / gated apply, all via OIDC (no secrets)
- [x] Applied dev → stage → prod; sites live at www / steve / dev / stage.cohns.net

## Phase 2 — Application platform ✅ complete

The containerized service + managed database + scalability story. **Compute runs on ECS Fargate,
not EKS** — a deliberate cost choice (a live Fargate service is ~$25–30/mo; an EKS control plane is
~$73/mo on top of the same pieces). The `live/compute` module could be swapped for EKS later; the
app, image, and database don't change.

- [x] FastAPI comments service — auth-gated, moderation queue, rate limiting **from the first
      commit** (`services/comments-api`); 11 tests, runs on SQLite (tests) or Postgres
- [x] Containerized; ECR repo + keyless build/push CI (`container-build.yml`)
- [x] `live/data` — Aurora PostgreSQL Serverless v2, **scale-to-zero** when idle; master password
      generated + rotated in Secrets Manager (never in state)
- [x] `live/compute` — ECS Fargate + ALB (public-subnet tasks, no NAT), regional ACM, DNS
- [x] Credentials at runtime: app reads the DB secret (task role); JWT signing key injected from
      Secrets Manager by ECS (execution role) — no secret in the image or plain env
- [x] Verified in dev: **https://api.dev.cohns.net** — post → moderate → publish over HTTPS;
      Aurora auto-pauses under light traffic (NullPool)
- [ ] `live/compute` is **currently torn down** to hold the bill at ~$0 — the ALB/ECS are gone
      (Aurora `comments-dev` stays up, scale-to-zero). Re-applying it is the trigger that lights up
      the dormant ALB observability (see Phase 4). Re-apply when there's a reason to demo the API.
- [ ] Apply stage / prod compute (dev only so far)
- [ ] EKS variant (Karpenter, AWS Load Balancer Controller, external-dns) — optional alternative;
      this is where Ansible would earn its keep (node bootstrap, config)

## Phase 3 — Content (mostly built)

Reordered: **cooking first**, then the (private) photo library. Nearly all of it is built, deployed,
and live; what genuinely remains is one tool and the resume. The rest is *content* (more recipes,
real lesson videos), not engineering.

- [x] **Cognito** — end-user identity as RS256/JWKS, not a shared HS256 secret. `cognito.tf` +
      `cognito-admin.tf` (cross-account admin) in shared-services; `live/compute` wires
      `COMMENTS_JWKS_URL` into the comments API, so it verifies Cognito tokens by group claim. The
      auth foundation the photo library needs.
- [x] **Cooking — recipes live.** The comments API (`api.cohns.net`, Fargate + Aurora Serverless
      scale-to-zero, prod) serves **7 recipes**; `site/js/recipes.js` renders them at `/recipes`
      (the `Loading…` placeholder is just the pre-fetch state). Import for these 7 was a one-off
      loader (`scripts/load_recipes.py`).
- [x] **Cooking — video.** `live/media` applied: ingest/output S3, `cohns-media-submit` Lambda,
      MediaConvert, `media.cohns.net` CloudFront. Proven end-to-end — a demo lesson transcoded to
      HLS (480/720 + poster). The recipe schema carries `video_key` and the page has an HLS.js
      player, so lessons drop in as content.
- [x] **Family photos — deployed and populated.** `live/family` + the `photo-library` module,
      applied in the prod content account: private S3 (**~2,870 photos**), a `cohns-family-list`
      Lambda behind API Gateway, invite-only `/family` landing (live, `noindex`). No facial
      recognition anywhere near it — see the blast-radius note in
      [account-layout.md](account-layout.md); the same reasoning applies to personal data about minors.
- [x] **Recipe import tool** — `scripts/import_recipe.py`: reads a page's schema.org/Recipe
      JSON-LD and emits the RecipeWrite shape for `load_recipes.py`. Honors robots.txt; keeps the
      copyright line by taking only facts (ingredients, steps), regenerating the summary from
      yield/times with attribution, and never lifting the headnote or images (drafts default to
      unpublished). Stdlib-only, 22 unit tests (`scripts/test_import_recipe.py`).
- [ ] **Resume** rendered from structured data rather than a checked-in PDF — not started.

## Phase 4 — Operations ✅ live in prod (2026-08-05)

Pulled ahead of the remaining Phase 3 content: observability is the part of this platform worth
showing, so it became a content area of its own —
**[cohns.net/observability](https://cohns.net/observability/)** (also on www / steve). Design
decisions and trade-offs are written up in [observability.md](observability.md).

- [x] Grafana Cloud (the "managed equivalent"), free tier — dashboards, data sources, synthetic
      checks, and alert wiring all as Terraform in `live/observability`. No click-ops.
- [x] Global synthetic monitoring of www / steve / dev from five probes, per-endpoint SLO panels —
      **public SLO board live**
- [x] CloudWatch read by a role Grafana Cloud **assumes** (external-id gated, read-only) — no access
      key issued to a vendor, consistent with the OIDC/Identity Center model. Trust:
      `arn:aws:iam::008923505280:root` (Grafana's us-west-0 data-source account) + `sts:ExternalId`.
- [x] Aurora scale-to-zero capacity + estimated $/hour as a **live public panel** — reads $0 at idle
      (the $/hour is a client-side transform: Grafana *public* dashboards 500 on CloudWatch
      metric-math)
- [x] `/metrics` on the comments API (prometheus-fastapi-instrumentator) for handler-level detail
- [x] Budget alerts per account (this is a personal project; a runaway bill is the realistic risk)
- [x] SNS paging path (topic + confirmed email) — kept on AWS so it doesn't depend on the dashboard
      vendor being up
- [x] Stack applied (dev) and **surfaced on the site** — links out rather than embeds: Grafana Cloud
      serves `X-Frame-Options: deny` and can't be iframed, so `/observability` renders link-out cards

**Dormant until `live/compute` is re-applied** (no ALB exists while compute is torn down; each is
gated so nothing renders as a false outage):
- [ ] RED dashboards from ALB metrics (built; gated on `enable_cloudwatch && enable_alb_alarms`)
- [ ] ALB CloudWatch alarms → SNS (5xx, p95 latency, unhealthy targets) — the topic is live; the
      alarms are gated on `enable_alb_alarms`
- [ ] Aurora "Database connections" panel — live board, but empty until traffic connects

**Still open:**
- [ ] SLO burn-rate alerting, once traffic makes the math meaningful
- [ ] Backup and restore drill — a backup nobody has restored is a hypothesis, not a backup
- [x] tflint, checkov, and Dependabot in CI — both scanners **gate** (checkov's
      initial 93-finding backlog triaged: genuine issues fixed, the rest documented in
      `.checkov.yaml` / inline `checkov:skip`); Dependabot batches weekly updates
