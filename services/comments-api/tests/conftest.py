import os
import time

# Configure the app for tests BEFORE importing it: an isolated SQLite file and a
# known JWT secret. Must happen before app modules read settings.
os.environ.setdefault("COMMENTS_DATABASE_URL", "sqlite+aiosqlite:///./test_comments.db")
os.environ.setdefault("COMMENTS_JWT_SECRET", "test-secret-at-least-32-bytes-long!!")

import jwt  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

import uuid  # noqa: E402

from sqlalchemy import insert  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, Category  # noqa: E402
from app.ratelimit import limiter  # noqa: E402

# The seed categories (mirrors migration 0004) — recipe tests reference these by
# name, and category validation now checks the DB, so seed them each fresh schema.
SEED_CATEGORIES = ["Breads", "Candy", "Quick Meals", "Appetizers", "Main Courses", "Desserts"]


@pytest_asyncio.fixture(autouse=True)
async def _fresh_db():
    # Rate limiting off by default so functional tests don't consume a budget;
    # the rate-limit test turns it back on. Fresh schema each test.
    limiter.enabled = False
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            insert(Category),
            [{"id": uuid.uuid4(), "name": n, "sort_order": i} for i, n in enumerate(SEED_CATEGORIES)],
        )
    yield
    await engine.dispose()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def make_token(sub: str = "user-1", name: str = "Alice", groups: list[str] | None = None) -> str:
    settings = get_settings()
    payload: dict = {"sub": sub, "name": name, "exp": int(time.time()) + 3600}
    if groups:
        payload["groups"] = groups
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
