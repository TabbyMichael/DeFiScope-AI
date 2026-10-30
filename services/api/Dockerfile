# DeFiScope AI - API image (multi-stage, non-root, healthchecked).

# --- Build stage: resolve dependencies into an isolated virtualenv ------------
# Alpine (musl) base: Docker Scout reports 0C/0H vs python:3.12-slim's 7C/17H.
# musllinux wheels cover pandas/numpy/pydantic-core/psycopg-binary/uvloop; the
# toolchain + image libs below are only used if a package falls back to sdist
# (e.g. reportlab). They live in the builder stage and are NOT copied to runtime.
FROM python:3.12-alpine AS builder

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

RUN apk add --no-cache build-base libjpeg-turbo-dev freetype-dev zlib-dev

COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev

# --- Runtime stage: minimal, non-root, only the venv + app source ------------
FROM python:3.12-alpine AS runtime

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Drop privileges: nothing in the container needs to run as root.
# Alpine/BusyBox uses addgroup/adduser (Debian's groupadd/useradd are absent).
RUN addgroup -g 1001 app && adduser -u 1001 -G app -h /home/app -D app

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
