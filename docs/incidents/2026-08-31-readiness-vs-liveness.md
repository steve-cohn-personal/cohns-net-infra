# Readiness vs liveness — the health check that lied

**A task that cannot reach its database is not healthy, and for the entire outage the load
balancer disagreed.** The comments API returned 500s to every request while its ALB target
group reported the target healthy, because the check asked whether the process was running
rather than whether it could do its job. Nothing recovered it. It took a manual restart.

This is the writeup of that, and of the general shape of mistake it belongs to.

## What happened

| | |
| --- | --- |
| **Impact** | The comments API returned 500s on every request. The static site was unaffected — it's CloudFront in front of S3 and has no dependency on the API. |
| **Started** | 2026-08-31 |
| **Detected** | By hand, on reading the site |
| **Resolved** | By hand, by restarting the task |
| **Root cause** | The ALB target group health check pointed at `/healthz`, a liveness probe that touches no dependency |
| **Fix** | `health_check_path = "/readyz"` in `terraform/live/compute` |

The trigger was the 7-day rotation of the RDS-managed master secret for `comments-prod`.
`Settings.build_database_url()` read the secret **once at import** and baked the password into
the engine URL, so the running task went on presenting the pre-rotation password and every
query failed with `asyncpg.exceptions.InvalidPasswordError`. The process itself never faltered;
it went on serving HTTP the whole time.

## Why nothing noticed

The app has two health endpoints and they mean different things:

```python
@app.get("/healthz", tags=["health"])
async def healthz():
    """Liveness — the process is up."""
    return {"status": "ok"}


@app.get("/readyz", tags=["health"])
async def readyz():
    """Readiness — the database is reachable."""
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return {"status": "ready"}
```

`/healthz` returns a literal. It cannot fail while the process can serve HTTP at all. It is the
right answer to "should this container be killed and restarted," and the wrong answer to
"should this target receive traffic."

The ALB was asking the second question and reading the first one's answer. So the failing task
stayed in rotation indefinitely: healthy by the only measure anyone was taking, broken by every
measure that mattered. ECS had no reason to replace it, because ECS replaces tasks that fail
*their* health check, and from the scheduler's point of view nothing was wrong.

Worse than a task that dies: a task that lies. A dead task gets replaced. This one sat there
answering.

## Where the bad default came from

The `fargate-service` module declares:

```hcl
variable "health_check_path" {
  description = "ALB target-group health check path."
  type        = string
  default     = "/healthz"
}
```

`/healthz` is the conventional name and the obvious default, which is exactly why it's dangerous.
Every caller that doesn't think about it inherits a check that can never fail. The module isn't
wrong to have a default — it's wrong to have *that* one. A general-purpose module can't know
what readiness means for a given service, but it can decline to guess in the direction that
always passes.

The fix is a caller override, with the reasoning written down next to it so the next person
doesn't quietly "simplify" it back:

```hcl
# The ALB checks readiness, not liveness. /healthz only proves the process is
# up; /readyz opens a database connection. A task that still answers /healthz
# but can no longer reach the database stays in service forever behind the
# former — which is how the API served 500s from 2026-08-31 until it was
# restarted by hand. Checking /readyz takes that task out of rotation and lets
# ECS replace it with one that works.
health_check_path = "/readyz"
```

Two lines of config. An outage that ran until somebody opened the site and noticed. The gap
between those two is the whole point of the writeup.

## The general shape of it

This is the same mistake as [the deploy script that checked the wrong thing](https://github.com/steve-cohn-personal/cohns-net-infra/issues/67):
**measuring a proxy for the state you care about, instead of the state you care about.**

- The ALB measured *is the process alive* as a proxy for *can this task serve requests*
- `deploy-api.sh` measured *what does the local tfvars file say* as a proxy for *what is actually
  running in the deployed task definition* — and the tfvars file is gitignored, so on a clean
  checkout it reported success having compared nothing. That one is fixed: since
  [#71](https://github.com/steve-cohn-personal/cohns-net-infra/pull/71) the check reads ECS

Both proxies are correlated with the truth most of the time, which is what makes them survive
review. Both fail in the specific case where you need them: when something has drifted. A check
that only agrees with reality when reality is fine is not a check.

The test worth applying to any health check, alarm, or deploy gate: **describe the failure it is
supposed to catch, then ask whether it would actually catch it.** If the answer requires a story
about how the process would also have crashed, the check is measuring the wrong thing.

## What changed

- `health_check_path = "/readyz"` in `live/compute`, with the reasoning in a comment
- An **unhealthy target** alarm now exists in `live/observability` — see
  [observability.md](../observability.md). The signal table there lists ALB target health as
  "catches a task that's up but not serving," which is this incident, encoded
- Synthetic monitoring probes the API from outside, so the next equivalent failure is caught by
  something that has no opinion about the server's internal state

That third one is the durable lesson. The blackbox probe would have caught this on day one
without knowing anything about `/healthz`, `/readyz`, or ECS — it just asks the same question a
user asks and believes the answer.

## Still open

- The module default is still `/healthz`. Every caller must remember to override it. A better
  module would require the caller to state a readiness path explicitly rather than defaulting to
  one that can't fail.
- Nothing alarms on *duration* of unhealthy state versus a flap. A sustained failure and a
  ninety-second deploy blip should not look the same.

---

*Incident date 2026-08-31. Fix shipped in [#64](https://github.com/steve-cohn-personal/cohns-net-infra/pull/64).*
