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
- [x] Live in dev: **https://api.dev.cohns.net** — post → moderate → publish verified over HTTPS;
      Aurora auto-pauses under light traffic (NullPool)
- [ ] Apply stage / prod compute (dev only so far)
- [ ] EKS variant (Karpenter, AWS Load Balancer Controller, external-dns) — optional alternative;
      this is where Ansible would earn its keep (node bootstrap, config)

## Phase 3 — Content

Reordered: **cooking first**, then the (private) photo library.

1. **Cooking — recipes + video (next).** Recipe content model, video transcoded by MediaConvert,
   served from CloudFront.
2. **Cognito** — a real token issuer for the comments API (replaces the HS256 shared secret with
   RS256/JWKS) and the auth foundation the photo library needs.
3. **Family photos.** Cognito invite-only signup, private S3, signed CloudFront URLs, `noindex`.
   No facial recognition anywhere near it. Not public, not indexed — see the blast-radius note in
   [account-layout.md](account-layout.md); the same reasoning applies to personal data about minors.
4. **Resume** rendered from structured data rather than a checked-in PDF.

## Phase 4 — Operations

- Prometheus + Grafana, or a managed equivalent
- CloudWatch alarms → SNS → phone
- Budget alerts per account (this is a personal project; a runaway bill is the realistic risk)
- Backup and restore drill — a backup nobody has restored is a hypothesis, not a backup
- tflint, tfsec/checkov, and Dependabot in CI
