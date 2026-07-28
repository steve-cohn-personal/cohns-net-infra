# Account Layout

Five accounts under one AWS Organization. The organizing principle is that **the account is
the blast radius** — IAM is subtle and easy to get wrong, while an account boundary is
absolute and hard to misconfigure.

```
Root (Organization)
│
├── management                    Billing, SCPs, Identity Center. No workloads. Ever.
│
├── OU: Infrastructure
│   └── shared-services           cohns.net DNS · Terraform state · ECR · org CloudTrail
│
└── OU: Workloads
    ├── dev                       dev.cohns.net
    ├── stage                     stage.cohns.net
    └── prod                      www.cohns.net · steve.cohns.net
```

## Why each one exists

**management** — Organizations root. The one account that can create accounts and attach SCPs,
so it holds nothing else worth attacking. Running a workload here is the single most common
multi-account mistake; the OU structure exists partly to make that impossible to do by accident.

**shared-services** — Things that are genuinely shared and shouldn't be duplicated: the
`cohns.net` public hosted zone, the Terraform state bucket, container registries, and the
org-wide CloudTrail archive. Workload accounts reach in through narrowly scoped roles.

**dev / stage / prod** — Identical infrastructure, different sizes. dev is disposable and
auto-applies on merge. stage is production-shaped so that a stage success means something.
prod is gated behind a human approval.

## DNS delegation

The apex `cohns.net` zone lives in shared-services. Each non-prod environment gets a
*delegated subzone* it fully owns:

```
cohns.net                (shared-services)
├── www      A/AAAA  →  prod CloudFront
├── steve    A/AAAA  →  prod CloudFront
├── dev      NS      →  dev account's zone
└── stage    NS      →  stage account's zone
```

The point: dev holds write access only to `dev.cohns.net`. There is no permission it could
misuse to break the apex, no matter how badly a plan goes wrong. Prod's pipeline assumes a
`Route53WriterFromProd` role in shared-services, scoped to the `www` and `steve` record sets.

## Regions

`us-west-2` primary. Two exceptions, both forced:

- **ACM certificates for CloudFront** must live in `us-east-1`. Hence the `aws.us_east_1`
  provider alias in the static-site module.
- **CloudFront and IAM** are global services with a `us-east-1` control plane.

An SCP restricts everything else to `us-west-2` and `us-east-1` — which also neatly limits the
damage from a compromised credential spinning up mining instances in a region nobody watches.

## Tagging

Applied via `default_tags` on every provider, so tagging is not something anyone has to
remember:

| Tag | Value |
| --- | --- |
| `Project` | `cohns.net` |
| `Environment` | `dev` / `stage` / `prod` |
| `ManagedBy` | `terraform` |
| `Repo` | `steve-cohn-personal/cohns-net-infra` |

`ManagedBy` and `Repo` matter more than they look: a year from now, anything untagged in these
accounts was created by hand and is a bug.

## Cost

Phase 1 runs at roughly **$3–8/month** — Route53 zones at $0.50 each, minimal S3, CloudFront
well inside the free tier, ACM free. Phase 2's EKS control plane adds ~$73/month per cluster,
which is exactly why the site ships before the cluster exists.
