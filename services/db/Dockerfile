# DeFiScope AI - database image: Postgres 16 + pgvector, on the Alpine base.
#
# Why not `pgvector/pgvector:pg16`? That third-party image is built on Debian
# `postgres:16-bookworm`; Docker Scout reported 9 Critical / 46 High CVEs and
# upstream had no rebuild to clear them. Alpine's `postgres:16` base reports
# ~4 Critical / 31 High and far fewer Low CVEs, and it's the same PostgreSQL 16
# engine (same wire protocol, driver and on-disk format), so the existing
# `pgdata` volume and the API's `postgresql+psycopg://` URL keep working as-is.
#
# Catch: the official `postgres:*-alpine` image compiles Postgres FROM SOURCE
# into /usr/local, so Alpine's packaged `postgresql-pgvector` (which installs to
# /usr/lib/postgresql) will NOT load against it. We therefore build pgvector
# from source against the image's own `pg_config` in a throwaway build stage and
# copy only the resulting extension files into the lean runtime image.
FROM postgres:16-alpine AS build

RUN apk add --no-cache build-base git

# Pin the extension version for a reproducible, auditable build. v0.8.7 matches
# what the previous pgvector image installed, so an existing pgdata cluster (whose
# catalog already records `vector` at 0.8.7) keeps working without a downgrade.
# `with_llvm=no` skips LLVM bitcode emission (the Postgres base was built with
# LLVM, so its makefiles default to clang, which we don't ship) - native .so only.
RUN git clone --branch v0.8.7 --depth 1 https://github.com/pgvector/pgvector.git /tmp/pgvector \
    && cd /tmp/pgvector \
    && make with_llvm=no \
    && make install with_llvm=no

# --- Runtime: same source-built Postgres base, plus the compiled extension ----
FROM postgres:16-alpine

# The build stage's `make install` wrote into /usr/local (matching this base's
# pg_config); copy just the pgvector artifacts so nothing else is dragged in.
COPY --from=build /usr/local/lib/postgresql/vector.so /usr/local/lib/postgresql/
COPY --from=build /usr/local/share/postgresql/extension/vector* /usr/local/share/postgresql/extension/

# Auto-create the extension on a brand-new cluster init. The app also issues an
# idempotent `CREATE EXTENSION vector` on every connect (db.py), so this is only
# belt-and-braces for a freshly initialized volume.
RUN echo 'CREATE EXTENSION IF NOT EXISTS vector;' > /docker-entrypoint-initdb.d/vector.sql
