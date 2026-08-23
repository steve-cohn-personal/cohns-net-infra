# comments-api: cost structure and the serverless question

**The goal: know exactly what the always-on API costs, and what it would take to make it
near-free — so the decision to keep paying is a choice rather than an oversight.** This is a
decision record, not a plan of work. The current decision is **keep the ALB + Fargate stack as
it is**; the reasoning and the levers are below, along with the triggers that should reopen it.

Measured 2026-08-23 against prod (`810100780414`). Dollar figures are us-west-2 list prices;
treat them as point-in-time.

## What it actually costs

Billing showed **$34.23 month-to-date, ~$46.08 forecast** — roughly double the "~$25/mo" figure
in [`comments-api-deploy.md`](comments-api-deploy.md). Nothing is runaway; that original estimate
predates AWS's 2024 public-IPv4 charge and omits it.

| Component | ~$/mo | Notes |
| --- | --- | --- |
| ALB `comments-prod` (hourly + LCU) | 17.50 | always-on; the single biggest line |
| 3 × public IPv4 | 10.95 | 2 on the ALB (one per AZ) + 1 on the Fargate task, @ $0.005/hr |
| Fargate 0.25 vCPU / 0.5 GB | 9.00 | one always-on task |
| Aurora storage, Route53, Secrets Manager, ECR, CloudFront/S3 | ~8.60 | the irreducible remainder |
| **Total** | **~46** | |

Two things that are *not* costing anything, so don't go hunting there:

- **Aurora compute is genuinely ~$0.** `min_capacity = 0` works — `ServerlessDatabaseCapacity`
  averages ~0.05 ACU over three days, spiking to 2.0 only during a deploy or migration.
- **The 4 KMS keys are AWS-managed** (no customer aliases), so $0, and the two Elastic IPs are
  the ALB's own — not strays.

Also verified: **dev, stage, and shared-services hold no ALB, no NAT gateway, no ECS cluster,
and no Aurora.** Dev compute is torn down as intended. The entire bill is prod.

The public-IPv4 charge is the direct cost of the "public subnets instead of a NAT gateway"
design in [`modules/network`](../terraform/modules/network/main.tf). That trade is still correct
— ~$11/mo of IPv4 beats ~$32/mo of NAT — it just isn't free the way it was when the module was
written.

## Why "just move it to Lambda like the photo library" does not work

The family photo library's Lambda is cheap because it has **no `vpc_config`** — it only touches
S3. That does not transfer. Aurora is in private subnets, so a Lambda must join the VPC; a
VPC-attached Lambda gets no public IP, and the network module has **no NAT gateway**. Fargate
reaches AWS APIs today only because it sits in a *public* subnet with a public IP, which Lambda
cannot do.

The service needs outbound to, per the code: **Secrets Manager**
([`config.build_database_url`](../services/comments-api/app/config.py)), the **Cognito JWKS
endpoint** (`PyJWKClient` in [`auth.py`](../services/comments-api/app/auth.py)), **STS +
cognito-idp** (the assume-role in [`aws_admin.py`](../services/comments-api/app/aws_admin.py)),
and **SNS** for signup/access notifications. S3 presigning is local signing and needs no call.

Covering those from inside the VPC costs **$7.30/mo per interface endpoint per AZ**. Four
endpoints costs more than the ALB it replaced. **A Lambda re-platform only pays off if the
function stays out of the VPC**, which means reaching Aurora over the **RDS Data API** —
currently `HttpEndpointEnabled: false`, though supported on this cluster (Aurora PostgreSQL
17.7, Serverless v2).

## The options, priced

| | Saves | New floor | App change | Risk |
| --- | --- | --- | --- | --- |
| **A.** Lambda + Data API, outside the VPC | ~$37 | ~$9 | rewrite the data layer | high |
| **B.** Lambda inside the VPC + interface endpoints | ~$8 | ~$38 | full rewrite | dominated — skip |
| **C.** Keep Fargate, drop the ALB (HTTP API + VPC Link → Cloud Map → ECS) | ~$25 | ~$21 | none | low–medium |

**A** is a rewrite, not a port. The data layer is SQLAlchemy 2.0 `AsyncSession` ORM across six
routers; there is no mature *async* Data API dialect, so every query and Alembic itself would
move to a different execution model. A container-image Lambda with Mangum would reuse the
existing ECR build, but that is the easy tenth of the job. It also stacks a Lambda cold start on
top of the Aurora resume already implied by `min_capacity = 0` — worth remembering for the
class-handout QR path, where the first scan pays both.

**C** removes the biggest line item with **no application code change**: a Cloud Map namespace,
`service_registries` on the ECS service, an HTTP API with a VPC Link private integration, the
custom domain on the existing ACM cert, repoint Route53, delete the ALB. Roughly half a day of
Terraform. Note the ALB cannot be shrunk to one AZ first — an ALB requires at least two subnets
in two AZs, so its two public IPv4 addresses are a floor while it exists.

## Two couplings that outlive any option

1. **The observability showcase is wired to the ALB.** `live/observability` carries three
   CloudWatch alarms (`alb_5xx`, `alb_latency`, `alb_unhealthy_hosts`) over
   `AWS/ApplicationELB`, plus the `dashboards/alb-red.json` RED dashboard. Removing the ALB
   dark-fires all of it. There is an `enable_alb_alarms` flag, so it is a clean seam, but the
   dashboards would need re-pointing at API Gateway or ECS metrics. See
   [`observability.md`](observability.md).
2. **`scripts/db-migrate.sh` dies with ECS.** It runs Alembic as a one-off Fargate task reusing
   the service's task definition and network. Option A removes ECS entirely and would need a new
   migration path (a migration Lambda, or CodeBuild). Option C keeps ECS, so migrations are
   untouched.

## Decision (2026-08-23): keep it, revisit on a trigger

**No re-platform for now.** Two reasons, and they both point the same way:

- **The stack is the product.** This site's premise is that the infrastructure is the portfolio,
  and during an active job search a live ALB + Fargate + Aurora + Cognito + CloudFront
  deployment with a RED dashboard over it is a working demonstration. Option C's first casualty
  is precisely that dashboard. Saving $25/mo by deleting the most legible piece of observability
  evidence is a bad trade while it is being shown to people.
- **It is not real money yet.** The account is covered by AWS customer-council usage credits, so
  the bill is not currently cash out the door. Optimising credit-funded spend at the cost of
  portfolio value is optimising the wrong variable.

**Reopen this when any of these change:**

- the usage credits lapse or stop covering the spend;
- the job search ends, and the demonstration value of the ALB/RED dashboard drops;
- traffic grows enough that Fargate needs a second task or larger size, which changes the
  arithmetic in favour of per-request billing;
- the observability story gets re-anchored on something other than ALB metrics (at which point
  Option C loses its main objection).

When it reopens, **Option C is the recommendation** — about 68% of the available saving for
roughly a tenth of the risk of Option A, with no application rewrite and no change to the
migration tooling. Option A only makes sense if going serverless becomes a goal in its own
right; the extra ~$12/mo does not justify a data-layer rewrite on its own.
