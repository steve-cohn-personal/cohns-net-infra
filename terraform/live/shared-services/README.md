# live/shared-services — Shared infrastructure

Runs against the **shared-services** account (`004161356168`). State lives in the management
account's bucket; the provider assumes `OrganizationAccountAccessRole` into shared-services, so
run it with the mgmt `admin` profile:

```sh
cd terraform/live/shared-services
AWS_PROFILE=admin terraform init
AWS_PROFILE=admin terraform apply
AWS_PROFILE=admin terraform output name_servers   # -> set these at the registrar
```

## What this manages

- `aws_route53_zone` for `cohns.net` — the apex public zone. Its nameservers go to the
  registrar **first**, since propagation gates ACM validation everywhere else.

## Still to come (separate steps)

- NS records delegating `dev.cohns.net` and `stage.cohns.net` to zones in those accounts
  (needs those zones to exist first).
- `Route53WriterFromProd` — a role assumable from prod, scoped to the `www` and `steve` record
  sets, so prod manages its own DNS without holding the zone.
- Org-wide CloudTrail and its locked log-archive bucket.
- ECR repositories (phase 2).

The Terraform state bucket is in the management account, built by
[`bootstrap/`](../../../bootstrap) — not here.
