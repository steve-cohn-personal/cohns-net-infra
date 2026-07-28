# cohns.net — Infrastructure as Code

The infrastructure behind [www.cohns.net](https://www.cohns.net), built with Terraform and
Ansible on AWS. This repository is public by design: it *is* the portfolio piece.

If you landed here from my resume — the interesting parts are
[docs/access-strategy.md](docs/access-strategy.md) for the identity model and
[docs/promotion.md](docs/promotion.md) for how code moves dev → stage → prod.

## What this builds

An AWS Organization with isolated dev/stage/prod accounts, human access via IAM Identity
Center, CI access via GitHub OIDC federation, and a CloudFront-fronted static site with a
containerized API to follow.

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
    account-baseline/ Guardrails applied to every member account.
    github-oidc/      Per-account CI deploy roles trusting GitHub's OIDC provider.
    static-site/      S3 + CloudFront + ACM + Route53.
  live/               One root module per account. Same code, different tfvars.
    org/              Management account: Organization, SCPs, Identity Center.
    shared-services/  DNS zone, state backend, ECR, org-wide CloudTrail.
    dev/ stage/ prod/ The workload accounts.
ansible/              Config management. Earns its keep in phase 2 (EKS nodes, app config).
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
- Ansible (phase 2)

## Getting started

One-time bootstrap is documented in [docs/bootstrap.md](docs/bootstrap.md). After that:

```sh
aws sso login --profile cohns-prod
make plan ENV=prod
```

## Status

Phase 1 — in progress. See [docs/roadmap.md](docs/roadmap.md).
