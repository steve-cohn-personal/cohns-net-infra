# cohns.net — Infrastructure as Code

The infrastructure behind [www.cohns.net](https://www.cohns.net), built with Terraform and
Ansible on AWS. This repository is public by design: it *is* the portfolio piece.

If you landed here from my resume — the interesting parts are
[docs/observability.md](docs/observability.md) for how the platform watches itself (and what it
costs to do so), [docs/access-strategy.md](docs/access-strategy.md) for the identity model, and
[docs/promotion.md](docs/promotion.md) for how code moves dev → stage → prod.

## What this builds

An AWS Organization with isolated dev/stage/prod accounts, human access via IAM Identity
Center, CI access via GitHub OIDC federation, CloudFront-fronted static sites, and a
containerized comments API on ECS Fargate backed by Aurora Serverless v2 — all deployed by
keyless pipelines.

**There are no credentials in this repository, and there never will be.** No access keys, no
state files, no `.tfvars` with account IDs. Humans authenticate with short-lived SSO
credentials; CI authenticates with OIDC and holds no secret at all. See
[docs/access-strategy.md](docs/access-strategy.md).

## Layout

```
bootstrap/            Chicken-and-egg: creates the S3 state backend using local state,
                      then migrates its own state into the bucket it just made.
terraform/
  modules/            Reusable modules, versioned with the repo.
    github-oidc/      Per-account CI roles trusting GitHub's OIDC provider (immutable subjects).
    static-site/      S3 + OAC + CloudFront + ACM + Route53.
    network/          VPC with public + private subnets (no NAT).
    aurora-serverless/ Aurora PostgreSQL Serverless v2, scale-to-zero.
    fargate-service/  ECS Fargate service behind an ALB.
  live/               One root module per concern; three environments via tfvars.
    org/              Management account: Organization, OUs, SCPs, Identity Center, CloudTrail.
    shared-services/  Apex DNS + email, ECR, CloudTrail archive, Route53WriterFromProd.
    site/             The static site (dev / stage / prod).
    data/             VPC + Aurora (dev / stage / prod).
    compute/          ECS Fargate comments API (dev / stage / prod).
    observability/    Grafana Cloud as code: synthetics, CloudWatch data source
                      (role-assumed, keyless), dashboards, alarms, cost budget.
services/
  comments-api/       FastAPI: auth-gated, moderated, rate-limited comments.
ansible/              Config management. Reserved for a future EKS/node story.
site/                 Static content served from S3.
docs/                 Architecture decisions and runbooks.
```

## Account layout

| Account | Purpose |
| --- | --- |
| management | Organizations root. Billing, SCPs, Identity Center. No workloads, ever. |
| shared-services | `cohns.net` public zone, Terraform state, ECR, org CloudTrail |
| dev | Where things get broken |
| stage | Production-shaped, production-sized-down. The promotion gate. |
| prod | `www.cohns.net`, `steve.cohns.net` |

`dev.cohns.net` and `stage.cohns.net` are delegated subzones owned by their respective
accounts, so a mistake in dev can never affect apex DNS.

## Prerequisites

- Terraform >= 1.10 (uses native S3 state locking via `use_lockfile`; no DynamoDB table)
- AWS CLI v2, configured for SSO
- Docker and Python >= 3.12 (to build and test the `comments-api` service)

## Getting started

One-time bootstrap is documented in [docs/bootstrap.md](docs/bootstrap.md). After that:

```sh
aws sso login --profile cohns-prod
make plan ENV=prod
```

## Status

- **Phase 1 — Foundation:** ✅ complete. Org, SSO, SCP guardrails, org CloudTrail, DNS + email,
  and static sites live at www / steve / dev / stage.cohns.net.
- **Phase 2 — Application platform:** ✅ complete. The comments API is live in dev at
  **https://api.dev.cohns.net** on ECS Fargate + Aurora Serverless v2, built and deployed by
  keyless CI. (Compute is Fargate rather than EKS — a deliberate cost choice.)
- **Phase 3 — Content:** cooking (recipes + video) next, then the private photo library.
- **Phase 4 — Operations:** in progress. The platform now watches itself — global synthetic
  probes, RED dashboards from ALB metrics, Aurora scale-to-zero capacity and cost, CloudWatch
  alarms → SNS, and a per-account budget — all Terraform, on Grafana Cloud's free tier for $0/mo.
  See [docs/observability.md](docs/observability.md).

See [docs/roadmap.md](docs/roadmap.md).
