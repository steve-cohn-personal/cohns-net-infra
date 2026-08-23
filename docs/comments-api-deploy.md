# Deploying the comments-api (dev)

Standing up `api.dev.cohns.net` so the recipes area (and visitor comments) run on
the real DB-backed API instead of the static `recipes-sample.json` fallback. The
service (`services/comments-api`) is fully built and CI-tested but has **never been
applied** — the always-on cost was the gate.

**Cost decision: approved at ~$26/mo (2026-07-30).** That estimate was low — it predates
AWS's 2024 public-IPv4 charge, and the real floor is **~$37/mo** (see the table below).
Measured prod spend and the re-platform options are in
[`comments-api-cost.md`](comments-api-cost.md).

## Current state

| Piece | Provides | Status |
| --- | --- | --- |
| `shared-services` | Cognito (JWKS / issuer / client), ECR repo | applied |
| `live/site` dev | delegated `dev.cohns.net` zone (`Z09826921EA4GXC49P5MT`) | applied |
| `live/data` dev | VPC + Aurora Serverless v2 + DB secret | **verify applied** |
| ECR image | `004161356168.dkr.ecr.us-west-2.amazonaws.com/cohns/comments-api:latest` | **verify present** |

The two "verify" rows need one `aws sso login --profile admin` to confirm before the
apply. The image is built and pushed by `.github/workflows/container-build.yml` on
pushes to `main` touching `services/comments-api/**`.

## What applying `live/compute` (dev) creates

ACM cert for `api.dev.cohns.net` (DNS-validated in the dev zone) → Application Load
Balancer in the public subnets (HTTPS + HTTP listeners, security groups) → ECS
Fargate cluster + one task running the image → Route53 A-alias `api.dev.cohns.net` →
ALB. The task role is granted read on exactly the DB secret; the app fetches its own
DB credentials at startup and, with `auto_create_tables = true`, **creates its schema
on first boot** — no separate migration step.

## Cost (dev, us-west-2)

| Item | Monthly | Notes |
| --- | --- | --- |
| ALB | ~$16–18 | fixed, always-on — the dominant cost |
| Public IPv4 | ~$11 | 3 addresses @ $0.005/hr: two on the ALB (one per AZ, and an ALB needs ≥2) plus one on the Fargate task |
| Fargate | ~$9 | 1 task, 0.25 vCPU / 0.5 GB (module minimum; `desired_count = 1`) |
| Aurora Serverless v2 | ~$0 idle | dev `min_acu = 0` → scale-to-zero; verified ~0.05 ACU average in prod |
| NAT gateway | $0 | network module deliberately omits it (tasks in public subnets) |
| ACM / Route53 / ECR | ~$0 | negligible |
| **Fixed floor** | **~$37/mo** | independent of traffic |

The IPv4 line is the price of the "public subnets instead of a NAT gateway" design in
`modules/network`. The trade is still right — ~$11/mo of IPv4 beats ~$32/mo of NAT — it
just stopped being free when AWS began charging for public IPv4 in 2024, after this
module was written.

If this floor ever becomes unwelcome, see [`comments-api-cost.md`](comments-api-cost.md)
for the priced options. Note that the obvious move — "do what the photo library does" —
**does not transfer**: that Lambda is cheap because it has no `vpc_config` and only
touches S3, whereas this service needs Aurora in private subnets. A VPC-attached Lambda
has no public IP and there is no NAT, so it would need interface endpoints for Secrets
Manager, Cognito JWKS, STS and SNS at ~$7.30/mo each per AZ — more than the ALB it
replaced. The realistic option is dropping the ALB while keeping Fargate (API Gateway
HTTP API + VPC Link → Cloud Map → ECS, ~$25/mo saved, no application change).

## Config gaps to fix first

1. **CORS (blocking).** `compute/env/dev.tfvars` does not set `cors_origins`, so it
   defaults to `www/steve.cohns.net` and the browser would block the `dev.cohns.net`
   site's fetch. Add `cors_origins = ["https://dev.cohns.net"]`.
2. **Aurora cold start.** `min_acu = 0` means the first request after idle resumes in
   a few seconds; the site shows the fallback meanwhile (graceful). Acceptable for dev.

## Execution plan

1. Confirm the ⚠️ dependencies (`live/data` dev applied; `:latest` image in ECR).
   Push `services/comments-api` to `main` if the image is missing (CI builds it).
2. Apply `live/data` dev if not already — VPC + Aurora + DB secret.
3. Add the dev `cors_origins` to `compute/env/dev.tfvars`.
4. Apply `live/compute` dev — cert validation + ALB + Fargate steady state (~5–10 min).
5. Verify: `curl https://api.dev.cohns.net/healthz` → 200; `GET /recipes` → `[]`.
6. Add the operator to the `moderators` Cognito group; obtain a moderator `id_token`
   (hosted-UI sign-in on the dev site).
7. `COHNS_MODERATOR_TOKEN=… ./scripts/load_recipes.py --env dev` — upserts the 7 recipes.
8. The site flips from the "preview content" banner to live API data.

## Rollback / teardown

`terraform destroy` on `live/compute` dev removes the ALB, Fargate service, cert, and
DNS record — dropping the monthly cost back to ~$0. The recipes remain visible via the
static `recipes-sample.json` fallback regardless.
