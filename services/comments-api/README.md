# comments-api

The visitor-comments service for cohns.net — a small FastAPI app that is **auth-gated,
moderated, and rate-limited from the first commit**, not retrofitted. This is the Phase 2
application the platform (EKS/Fargate + Aurora) will eventually run.

## Design

- **Moderation by default.** Every comment is created `pending`; the public read path
  (`GET /comments`) only ever returns `approved`. A compromised or abused posting path cannot
  publish anything on its own.
- **Auth is Cognito-ready.** Posting requires a valid JWT bearer token; moderation requires a
  `moderators` group claim. Verification is HS256 with a shared secret today; set
  `COMMENTS_JWKS_URL` to a Cognito user-pool JWKS endpoint and it switches to RS256 with no other
  code change (see [`app/auth.py`](app/auth.py)).
- **Rate limited** per client IP on `POST /comments` (slowapi). In-memory by default; point
  `COMMENTS_RATE_LIMIT_STORAGE` at Redis/ElastiCache once there is more than one replica.
- **Private data stays private.** The public schema never returns the author's subject id.
- **Health probes** (`/healthz` liveness, `/readyz` readiness) for Kubernetes.

## Endpoints

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `GET` | `/comments?page_slug=…` | none | Approved comments for a page |
| `POST` | `/comments` | user | Submit a comment (lands `pending`) |
| `GET` | `/admin/comments?status_filter=pending` | moderator | The moderation queue |
| `POST` | `/admin/comments/{id}/moderate` | moderator | Approve or reject |
| `GET` | `/healthz`, `/readyz` | none | Liveness / readiness |

## Run it locally

With Docker (Postgres, mirrors prod):

```sh
docker compose up --build
curl localhost:8000/healthz
```

Without Docker (SQLite, no services):

```sh
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
COMMENTS_JWT_SECRET=local-dev-secret-at-least-32-bytes-long uvicorn app.main:app --reload
```

## Test

```sh
pip install -e '.[dev]'
pytest
```

Tests run on async SQLite — no database to stand up.

## Migrations

The schema is owned by Alembic in production (`COMMENTS_AUTO_CREATE_TABLES=false`, run
`alembic upgrade head` as an init step). Locally, `COMMENTS_AUTO_CREATE_TABLES=true` creates
tables on boot for convenience.

## Database credentials

Two ways to get a connection, chosen by config:

- **Local / tests** — `COMMENTS_DATABASE_URL` directly (SQLite, or the compose Postgres).
- **Production** — set `COMMENTS_DB_SECRET_ARN` to the RDS-managed master secret (from `live/data`'s
  `db_secret_arn` output). At startup the app reads the username/password from Secrets Manager and
  combines them with `COMMENTS_DB_HOST` (the cluster endpoint), `COMMENTS_DB_PORT`, and
  `COMMENTS_DB_NAME` (`commentsdb`). **No credential is ever in env, a tfvars, or the image.** The
  task/pod role attaches `live/data`'s `db_read_secret_policy_arn` to be allowed `GetSecretValue` on
  just that one secret.

## Configuration

All via `COMMENTS_`-prefixed environment variables (see [`app/config.py`](app/config.py)):
`DATABASE_URL`, `DB_SECRET_ARN`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `AWS_REGION`,
`JWT_SECRET` / `JWKS_URL`, `MODERATOR_GROUP`, `RATE_LIMIT_POST`, `RATE_LIMIT_STORAGE`,
`CORS_ORIGINS`, `AUTO_CREATE_TABLES`.
