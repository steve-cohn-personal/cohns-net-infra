# Multi-stage: build a venv with the Postgres driver, then copy it into a slim,
# non-root runtime. Pinned to 3.12 for stable wheels (incl. asyncpg).

FROM python:3.12-slim AS builder
WORKDIR /build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
COPY pyproject.toml ./
COPY app ./app
RUN python -m venv /venv && /venv/bin/pip install --upgrade pip && /venv/bin/pip install ".[postgres]"

FROM python:3.12-slim
RUN groupadd --system app && useradd --system --gid app --home /app app
WORKDIR /app

COPY --from=builder /venv /venv
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./

ENV PATH="/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    COMMENTS_AUTO_CREATE_TABLES=false

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/healthz').status==200 else 1)"

# --proxy-headers so the real client IP (X-Forwarded-For from CloudFront/ALB) is
# used for rate limiting.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
