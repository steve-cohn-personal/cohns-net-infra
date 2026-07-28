# Roadmap

## Phase 1 — Foundation (in progress)

Deliverables: an access strategy, an account layout with a promotion path, a public repo with
no credentials in it, and a live site.

- [x] Repository scaffolding, `.gitignore` hardened for a public repo
- [x] `bootstrap/` — versioned, encrypted, TLS-only state backend with native S3 locking
- [x] `modules/static-site` — S3 + OAC + CloudFront + ACM + Route53, strict CSP
- [x] `modules/github-oidc` — keyless CI, scoped by repo/branch/environment
- [x] `live/site` — one root module, three environments
- [x] CI: fmt, validate, per-environment plan, gated apply
- [x] Placeholder site
- [ ] Organization + member accounts (`live/org`) — **blocked on AWS credentials**
- [ ] IAM Identity Center permission sets and assignments
- [ ] SCP guardrails and org-wide CloudTrail
- [ ] `live/shared-services` — hosted zone, subzone delegation
- [ ] Apply dev → stage → prod; site live at www.cohns.net

## Phase 2 — Application platform

The Kubernetes, database, and scalability story.

- FastAPI service, containerized, built and pushed to ECR by CI
- EKS via the community module; Karpenter for node autoscaling
- Aurora Serverless v2 Postgres; credentials in Secrets Manager with rotation
- ALB ingress via the AWS Load Balancer Controller, external-dns for Route53
- Ansible earns its place here: node bootstrap, app config, local dev environment
- Comments API — auth-gated posting, moderation queue, rate limiting **from the first commit**,
  not retrofitted

## Phase 3 — Content

- **Cooking**: recipe content model, video transcoded by MediaConvert, served from CloudFront
- **Family photos**: Cognito with invite-only signup, private S3, signed CloudFront URLs,
  `noindex`. No facial recognition anywhere near it. This area is not public and is not indexed —
  see the note in [account-layout.md](account-layout.md) about blast radius; the same reasoning
  applies to personal data about minors.
- Resume rendered from structured data rather than a checked-in PDF

## Phase 4 — Operations

- Prometheus + Grafana, or a managed equivalent
- CloudWatch alarms → SNS → phone
- Budget alerts per account (this is a personal project; a runaway bill is the realistic risk)
- Backup and restore drill — a backup nobody has restored is a hypothesis, not a backup
- tflint, tfsec/checkov, and Dependabot in CI
