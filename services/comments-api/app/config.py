from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration, read from the environment (12-factor).

    Nothing secret has a real default — the JWT secret must be supplied. The DB
    default is a local SQLite file so the app and tests run with no services.
    """

    model_config = SettingsConfigDict(env_prefix="COMMENTS_", env_file=".env", extra="ignore")

    # Async SQLAlchemy URL. Local: sqlite+aiosqlite. Prod: postgresql+asyncpg://...
    database_url: str = "sqlite+aiosqlite:///./comments.db"

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
