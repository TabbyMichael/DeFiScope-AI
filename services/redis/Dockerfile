# DeFiScope AI - catalog cache container: Redis 7 with a cache-tuned config.
#
# Why a build folder for an otherwise-stock image? Same reason as services/db:
# pin the base and bake in the little configuration this role actually needs,
# instead of running `image: redis:7-alpine` on Redis's defaults - and the
# defaults are actively wrong for a disposable read cache. Out of the box Redis
# leaves `maxmemory` unset (so it grows until the host OOMs) and sets
# `maxmemory-policy noeviction` (so under pressure it REFUSES writes rather than
# dropping cold entries). services/redis/redis.conf fixes both: a bounded cache
# that evicts least-recently-used pages, plus AOF so warm pages survive a
# restart. It is still strictly optional at runtime: remove this container, or
# unset DEFISCOPE_REDIS_URL, and the API degrades to serving every catalog read
# straight from Postgres. The cache is a speedup, never a dependency or a source
# of truth (Postgres is).
FROM redis:7-alpine

# The official image's entrypoint execs CMD when it starts with `redis-server`,
# so handing it the baked config is all that is needed. `--include` would let an
# operator layer site overrides at runtime without rebuilding, but nothing is
# shipped there today.
COPY redis.conf /usr/local/etc/redis/defiscope-redis.conf

CMD ["redis-server", "/usr/local/etc/redis/defiscope-redis.conf"]
