# DeFiScope AI - API image (multi-stage, non-root, healthchecked).

# --- Build stage: resolve dependencies into an isolated virtualenv ------------
FROM python:3.12-slim AS builder

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev

# --- Runtime stage: minimal, non-root, only the venv + app source ------------
FROM python:3.12-slim AS runtime

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Drop privileges: nothing in the container needs to run as root.
RUN groupadd --gid 1001 app && useradd --uid 1001 --gid app --create-home app

COPY --from=builder /app/.venv /app/.venv
COPY app ./app

# Writable home for the SQLite fallback path; Postgres is used in compose.
USER app

EXPOSE 8000

# Readiness probe: /api/health/ready returns 503 until the DB answers SELECT 1,
# so this also acts as a dependency-aware gate for compose/k8s. Uses the venv's
# interpreter (no curl in slim). start-period gives the warm-up pass time.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import sys,urllib.request as u; sys.exit(0 if u.urlopen('http://127.0.0.1:8000/api/health/ready', timeout=3).status==200 else 1)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
