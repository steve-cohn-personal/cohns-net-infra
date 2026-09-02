from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration, read from the environment (12-factor).

    Nothing secret has a real default — the JWT secret must be supplied. The DB
    default is a local SQLite file so the app and tests run with no services.
    """

    model_config = SettingsConfigDict(env_prefix="COMMENTS_", env_file=".env", extra="ignore")

    # Async SQLAlchemy URL. Local/tests: sqlite+aiosqlite. Used directly unless
    # db_secret_arn is set (see build_database_url).
    database_url: str = "sqlite+aiosqlite:///./comments.db"

    # Production database via Secrets Manager. When db_secret_arn is set, the
    # username/password are read from that secret (the RDS-managed master secret)
    # on every new connection and combined with the host/port/name below — so no
    # credential is ever in env, a tfvars, or an image. host/port/name come from
    # the cluster endpoint (live/data outputs), which are not secret.
    db_secret_arn: str | None = None
    db_host: str | None = None
    db_port: int = 5432
    db_name: str = "commentsdb"
    aws_region: str = "us-west-2"

    # Disable connection pooling (NullPool): open a connection per request and
    # close it immediately, so nothing keeps the database open between requests.
    # This lets an Aurora Serverless v2 cluster with min_capacity 0 auto-pause when
    # idle — trading a few seconds of resume latency on the first request after a
    # pause for a near-$0 idle bill. Worth it for a light-traffic service.
    db_nullpool: bool = False

    # TLS to Postgres. Aurora PostgreSQL 16+ ships rds.force_ssl=1, so the server
    # rejects unencrypted connections ("no pg_hba.conf entry ... no encryption").
    # asyncpg's own default is "prefer", which silently DOWNGRADES to plaintext and
    # is then refused — so default to "require" here: encrypted unless deliberately
    # turned off. Set "disable" for a local plaintext Postgres (see docker-compose).
    # Ignored for SQLite.
    db_sslmode: str = "require"

    # JWT verification. HS256 with a shared secret is the local/first-commit mode.
    # Setting jwks_url (a Cognito user-pool JWKS endpoint) switches to RS256 later
    # without touching the rest of the app — see app/auth.py.
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_issuer: str | None = None
    jwt_audience: str | None = None
    jwks_url: str | None = None

    # A token carrying this value in its "groups" (or "scope") claim may moderate.
    moderator_group: str = "moderators"

    # User administration (grant/revoke group membership) and access-request emails.
    # The Cognito pool lives in another account, so the task assumes this role to
    # call the admin APIs; both are None locally/in tests (the endpoints then 503).
    # Only these groups may be granted/revoked through the admin API.
    cognito_pool_id: str | None = None
    cognito_admin_role_arn: str | None = None
    grantable_groups: list[str] = ["family", "moderators"]
    # SNS topic that emails on a new access request. None = requests are accepted
    # but no notification is sent.
    access_request_topic_arn: str | None = None
    # SNS topic that emails on a class signup/request. None = no notification sent
    # (the signup/request still succeeds and persists).
    class_topic_arn: str | None = None

    # Media uploads. Moderators upload recipe images (and, later, lesson videos)
    # straight to S3 via a presigned PUT the API mints. The buckets belong to the
    # prod-only media stack and are in this account, so the task role's own creds
    # sign the URL (no assume-role). All None locally/in tests and in dev (no dev
    # media stack) → the presign endpoint 503s. media_cdn_base is the public origin
    # the output bucket is served from (https://media.cohns.net).
    media_output_bucket: str | None = None
    media_ingest_bucket: str | None = None
    media_cdn_base: str | None = None

    # Rate limit for posting, in slowapi syntax. Applied per client IP.
    rate_limit_post: str = "5/minute"

    # slowapi storage. memory:// is per-process — fine for one replica, but the
    # limit is not shared across pods. Point at redis://... (ElastiCache) once the
    # service runs more than one replica.
    rate_limit_storage: str = "memory://"

    # Comment body length bounds.
    body_min_length: int = 1
    body_max_length: int = 4000

    # CORS origins allowed to call the API (the site fronts it).
    cors_origins: list[str] = ["https://www.cohns.net", "https://steve.cohns.net"]

    # Create tables on startup. Convenient for local SQLite; in prod this is False
    # and Alembic migrations own the schema.
    auto_create_tables: bool = True

    # Expose Prometheus RED metrics at /metrics. On by default; the metrics are
    # request counts and latency histograms (no bodies, no credentials), so the
    # endpoint is safe to leave reachable. Set COMMENTS_METRICS_ENABLED=false to
    # turn it off entirely.
    metrics_enabled: bool = True

    def fetch_db_credentials(self) -> tuple[str, str]:
        """Read the current username/password from the RDS-managed master secret.

        Called for each new database connection (app/db.py), not once at import.
        That secret rotates on a schedule, and a process still holding the password
        it read at boot fails every query the moment rotation happens — which is
        what took the API down on 2026-08-31, with the ALB none the wiser because
        it was health-checking /healthz.

        boto3 is imported lazily so local/test runs never need it.
        """
        import json

        import boto3

        client = boto3.client("secretsmanager", region_name=self.aws_region)
        secret = json.loads(client.get_secret_value(SecretId=self.db_secret_arn)["SecretString"])
        return secret["username"], secret["password"]

    def build_database_url(self) -> str:
        """The effective async SQLAlchemy URL.

        With db_secret_arn set, the URL carries only dialect/host/port/database —
        the credentials are supplied per connection by app/db.py, so nothing here
        goes stale. Otherwise use database_url as-is.
        """
        if not self.db_secret_arn:
            return self.database_url

        host = self.db_host or ""
        return f"postgresql+asyncpg://{host}:{self.db_port}/{self.db_name}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
