# live/org — Management account

The Organization, its OU structure, and the member accounts. Applied with SSO admin credentials
in the management account (`aws sso login --profile admin`).

## What this manages

- `aws_organizations_organization` — **imported**, not created. The org (`o-ajlh1xjt64`) has
  existed since 2019. Its `aws_service_access_principals` and `enabled_policy_types` are pinned
  to the live values on purpose; changing them here changes trusted access for the whole org.
- `aws_organizations_organizational_unit` — `Infrastructure` and `Workloads`.
- `aws_organizations_account` × 4 — `cohns-shared-services` (Infrastructure), `cohns-dev`,
  `cohns-stage`, `cohns-prod` (Workloads). Created fresh; the suspended 2019 accounts are left
  to age out and are not reused.

Still to come (separate, deliberate steps — not in this first apply): SCP guardrails, the
Identity Center permission sets from [access-strategy.md](../../../docs/access-strategy.md), and
org-wide CloudTrail.

## First run

```sh
cd terraform/live/org
cp org.example.tfvars org.auto.tfvars   # then fill in real, unique account emails
terraform init
terraform import aws_organizations_organization.this o-ajlh1xjt64
terraform plan     # expect: org unchanged, 2 OUs + 4 accounts to add
terraform apply
```

`org.auto.tfvars` holds the member-account root emails and is gitignored — those addresses are
the root identity of every account and never belong in a public repo.

Account creation is asynchronous; a few minutes per account is normal. The accounts carry
`prevent_destroy` and `close_on_deletion = false` — Terraform will never close an account, by
design. Closing one is a manual, 90-day, irreversible act.

## Outputs

`account_ids` and `account_admin_role_arns` feed the downstream modules — live/site backends,
DNS subzone delegation, and the per-account provider `assume_role` blocks.
