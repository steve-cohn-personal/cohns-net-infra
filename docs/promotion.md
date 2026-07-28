# Promotion: dev → stage → prod

## The core idea

There is **one** root module: [`terraform/live/site`](../terraform/live/site). All three
environments run that same code. What differs is a tfvars file and a backend key.

```sh
terraform init -reconfigure -backend-config=env/stage.backend.hcl
terraform apply -var-file=env/stage.tfvars
```

This matters more than it looks. The common alternative — a directory per environment with
copy-pasted `main.tf` files — drifts. Someone fixes a bug in prod, forgets dev, and six months
later stage no longer predicts anything. Here it is not a similar configuration; it is *the
same configuration*, so a successful stage apply is real evidence about prod.

Differences between environments are visible in one place: three short tfvars files you can
read side by side.

## The pipeline

```
  PR opened
     │
     ├─ fmt + validate
     └─ plan × {dev, stage, prod}      ← three plans on the PR. Reviewers see
     │                                    exactly what prod will do before merge.
  merge to main
     │
     ├─ terraform apply → dev          ← automatic
     └─ site sync      → dev
     │
  workflow_dispatch(stage)
     │
     └─ apply + deploy → stage         ← manual trigger
     │
  workflow_dispatch(prod)
     │
     └─ [required reviewer approves]   ← the gate
        apply + deploy → prod
```

## Where the gate actually lives

The prod approval is a **GitHub Environment protection rule**, not a step in the workflow file.
That's deliberate: a gate defined in the YAML can be removed by the same pull request that
changes the infrastructure. An Environment's required-reviewer setting lives in repository
settings, outside the diff.

The same boundary is enforced on the AWS side. The prod deploy role's trust policy accepts
`repo:...:environment:prod` and no branch at all — so even a workflow that skipped the gate
could not obtain prod credentials. Two independent controls, neither sufficient alone.

## Content vs. infrastructure

Two workflows, on purpose:

- [`terraform.yml`](../.github/workflows/terraform.yml) — infrastructure. Slow, gated, plans reviewed.
- [`site-deploy.yml`](../.github/workflows/site-deploy.yml) — content. Fast, sync and invalidate.

Fixing a typo shouldn't require a Terraform plan, and a Terraform change shouldn't silently
republish content.

## Rollback

- **Content** — the origin bucket is versioned; re-sync from a previous commit and invalidate.
- **Infrastructure** — revert the commit and re-apply. State is versioned in S3, so a corrupted
  state file is recoverable independently of the resources it describes.
- **Certificates and DNS** — the slow ones. ACM validation and NS propagation are measured in
  minutes to hours, which is a good reason to make DNS changes early in a session, not late.
