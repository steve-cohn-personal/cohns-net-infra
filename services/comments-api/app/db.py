import asyncio
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings

_settings = get_settings()
_url = _settings.build_database_url()

# SQLite needs check_same_thread off. For Postgres, pass the TLS mode explicitly:
# asyncpg defaults to "prefer", which falls back to an unencrypted connection that
# Aurora (rds.force_ssl=1) then rejects — a failure that only surfaces once the
# instance restarts and the dynamic parameter takes effect. See Settings.db_sslmode.
_connect_args = (
    {"check_same_thread": False}
    if _url.startswith("sqlite")
    else {"ssl": _settings.db_sslmode}
)

# NullPool holds no idle connections (lets Aurora auto-pause); otherwise pool and
# pre-ping to weed out stale connections.
_pool_kwargs = {"poolclass": NullPool} if _settings.db_nullpool else {"pool_pre_ping": True}


# --- Credentials that rotate ------------------------------------------------
# The RDS-managed master secret rotates on a schedule (currently every 7 days).
# Reading it once at import and baking the password into the engine URL means the
# process goes on presenting the old password afterwards, and every query fails
# with InvalidPasswordError until someone restarts the task — an outage on a
# timer. So cache the credentials, hand them to asyncpg per connection, and
# re-read the secret once if the password is refused.

_credentials: tuple[str, str] | None = None
_credentials_lock = asyncio.Lock()


async def _get_credentials(*, refresh: bool) -> tuple[str, str]:
    global _credentials
    async with _credentials_lock:
        if refresh or _credentials is None:
            # boto3 is blocking; keep it off the event loop.
            _credentials = await asyncio.to_thread(_settings.fetch_db_credentials)
        return _credentials


async def _connect():
    """One asyncpg connection, using whatever the password is right now."""
    import asyncpg

    for refresh in (False, True):
        user, password = await _get_credentials(refresh=refresh)
        try:
            return await asyncpg.connect(
                host=_settings.db_host or "",
                port=_settings.db_port,
                database=_settings.db_name,
                user=user,
                password=password,
                ssl=_settings.db_sslmode,
            )
        except asyncpg.InvalidPasswordError:
            # The secret rotated under us: re-read it and try exactly once more.
            # A second refusal is a real credential problem, not a stale cache.
            if refresh:
                raise
    raise RuntimeError("unreachable")


if _settings.db_secret_arn:
    engine = create_async_engine(_url, async_creator=_connect, **_pool_kwargs)
else:
    engine = create_async_engine(_url, connect_args=_connect_args, **_pool_kwargs)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, committed on success."""
    async with SessionLocal() as session:
        yield session
