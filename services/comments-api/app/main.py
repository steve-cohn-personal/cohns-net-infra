from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

from app.config import get_settings
from app.db import engine
from app.models import Base
from app.ratelimit import limiter
from app.routers import admin_users, classes, comments, moderation, recipes

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auto_create_tables:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title="cohns.net content API",
    version="0.2.0",
    summary="Auth-gated, moderated comments; authored recipes with lesson videos.",
    lifespan=lifespan,
)

# Rate limiting: attach the limiter and return 429 (not 500) when a limit trips.
app.state.limiter = limiter


async def _rate_limited(request, exc):  # slowapi handler signature
    from slowapi import _rate_limit_exceeded_handler

    return _rate_limit_exceeded_handler(request, exc)


app.add_exception_handler(RateLimitExceeded, _rate_limited)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(comments.router)
app.include_router(moderation.router)
app.include_router(recipes.router)
app.include_router(classes.router)
app.include_router(admin_users.router)
app.include_router(admin_users.requests_router)


# Prometheus RED metrics at /metrics: request rate, errors, and a latency
# histogram, labelled by method / handler / status. Grafana Cloud scrapes this
# via an Alloy sidecar when app-level metrics are wanted; the live dashboards
# also derive rate/errors/duration from ALB CloudWatch metrics, so this endpoint
# is additive, not load-bearing. Health and metrics paths are excluded so they
# don't inflate the latency histogram.
if settings.metrics_enabled:
    Instrumentator(excluded_handlers=["/metrics", "/healthz", "/readyz"]).instrument(
        app
    ).expose(app, endpoint="/metrics", include_in_schema=False)


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
