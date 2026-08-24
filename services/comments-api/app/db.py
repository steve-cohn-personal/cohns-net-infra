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

engine = create_async_engine(_url, connect_args=_connect_args, **_pool_kwargs)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, committed on success."""
    async with SessionLocal() as session:
        yield session
