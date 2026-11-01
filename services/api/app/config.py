"""Application settings loaded from environment / .env file."""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="DEFISCOPE_", extra="ignore")

    # Data sources
    defillama_base_url: str = "https://api.llama.fi"
    # Additional DefiLlama hosts for the fees / revenue / volume enrichment
    # (Increment D). They reuse the same retry/backoff as the TVL client and are
    # fetched best-effort: any failure degrades to a data gap, never a crash.
    fees_base_url: str = "https://fees.llama.fi"
    coins_base_url: str = "https://coins.llama.fi"
    # Master switch for the extra fee/volume fetches during a crawl. Disable to
    # fall back to TVL-only requests (e.g. if the fees host is rate-limiting).
    economic_data_enabled: bool = True
    # Master switch for the stablecoin peg-history fetch (Increment E), which
    # reads price history from coins.llama.fi above. Disable to skip the depeg
    # watch entirely (the indicator then surfaces as a data gap).
    stablecoin_data_enabled: bool = True
    # Lookback window (days) for peg-deviation history from coins.llama.fi.
    depeg_window_days: int = 30
    http_timeout_seconds: float = 30.0

    # --- On-chain activity (second data provider: Dune Analytics) ------------
    # Deliberately additive: DefiLlama stays the source of TVL, fees, revenue,
    # prices and history. Dune supplies contract-level activity (active wallets,
    # transaction count, transfer volume, returning wallets) that no TVL feed
    # can express. Nothing here feeds the seven risk indicators - see
    # docs/methodology.md for why that stays a separate, calibrated decision.
    dune_base_url: str = "https://api.dune.com/api/v1"
    # Backend-only secret. NEVER publish it through a NEXT_PUBLIC_* variable.
    dune_api_key: str | None = None
    # Id of the single saved Dune query returning all four activity metrics.
    dune_activity_query_id: int | None = None
    # Master switch for the whole feature. Even when enabled, nothing runs
    # unless the key AND the query id are both present - the same "only build
    # it when its inputs exist" rule the notification channels follow. With
    # either missing, on-chain data reports an explicit data gap, never zeros.
    onchain_data_enabled: bool = True
    dune_max_retries: int = 3
    # Wall-clock ceiling for one execution (execute -> poll -> results). On
    # expiry the slug is skipped and retried next pass: a slow query must never
    # hold a 30-minute monitoring pass hostage.
    dune_poll_timeout_seconds: float = 120.0
    dune_poll_interval_seconds: float = 3.0
    # Dune's own server-side result cache. One execution per (slug, chain) per
    # day is the steady state; a shorter window would spend credits re-running
    # SQL whose answer cannot have changed.
    dune_result_max_age_seconds: int = 86400
    # Window (days) the saved query aggregates over.
    dune_lookback_days: int = 30
    # Credit and latency budget: at most this many protocols are refreshed per
    # monitoring pass, round-robin, so a large watchlist drains over several
    # passes instead of stalling one of them.
    dune_max_protocols_per_pass: int = 8

    # HTTP resilience: extra attempts (beyond the first) for transient
    # 429/5xx/transport errors when talking to DefiLlama. 0 disables retries.
    defillama_max_retries: int = 3

    # Persistence
    database_url: str = "sqlite:///./defiscope.db"

    # --- Redis response cache (optional; performance roadmap Stage 3) --------
    # A strictly-optional accelerator for the catalog list/facet read path - the
    # only hot surface without an in-process cache. When ``redis_url`` is unset
    # (the default) every cache helper no-ops and reads use the exact database
    # path they use today: a speedup when present, never a dependency. Postgres
    # stays the source of truth; Redis holds only disposable, TTL-bounded pages.
    redis_url: str | None = None
    # Master switch; effective only when ``redis_url`` is also set. Disable to
    # fall back to uncached DB reads without removing the Redis service.
    catalog_cache_enabled: bool = True
    # Catalog pages change only via a sync, which bumps a namespace version (so
    # staleness is bounded by invalidation, not just TTL); keep the TTL short.
    catalog_cache_ttl_seconds: int = 60
    # Facets are a cheap distinct scan that changes only when a brand-new chain
    # or category first appears, so they tolerate a longer TTL.
    facets_cache_ttl_seconds: int = 300

    # --- Authentication & authorization (roadmap #17) ------------------------
    # off      -> every request is served a synthetic, unrestricted principal.
    #             The legacy showcase/CI posture; NEVER safe for a public deploy.
    # demo     -> local login required, seeded demo accounts, role switching.
    # required -> local login required, no seeds, no role switching.
    auth_mode: str = "demo"
    auth_session_hours: int = 12
    auth_cookie_name: str = "defiscope_session"
    # Lifetime of the single-use WebSocket ticket the browser fetches before
    # opening WS /ws/chat (the socket cannot carry an httpOnly cookie across
    # hosts, so the session is exchanged for a short-lived ticket instead).
    auth_ws_ticket_seconds: int = 60
    # Published on the login page; only seeded when auth_mode == "demo".
    auth_demo_password: str = "defiscope-demo"

    # Browser origins allowed to call the API. Server-side RSC fetches bypass
    # CORS, but the docs link and any client-side calls need the caller origin
    # listed - hence the web dev (3000/3001) and docker-web (4000) ports.
    cors_allow_origins: str = (
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:3001,http://127.0.0.1:3001,"
        "http://localhost:4000,http://127.0.0.1:4000"
    )

    # Curated watchlist (DefiLlama slugs), always tracked on top of the
    # market-wide auto-discovery below.
    default_protocols: str = (
        "aave-v3,uniswap-v3,lido,curve-dex,compound-v3,"
        "makerdao,sky,rocket-pool,ether.fi,pancakeswap,"
        "balancer,sushi,jupiter,pendle,morpho,fluid"
    )

    # Market-wide tracking: auto-include the top N protocols by TVL from the
    # DefiLlama directory (deduplicated against the curated list). 0 disables.
    market_top_n: int = 50

    # Directory categories excluded from auto-discovery. CEX wallets, canonical
    # bridge locks and chain-infrastructure totals are custody/consensus sums,
    # not composable DeFi TVL - they would dwarf the real market.
    excluded_categories: str = "CEX,Bridge,Canonical Bridge,Chain,RPC"

    # Individual slugs excluded from discovery regardless of category (e.g.
    # exchange-operated staking products listed under legit categories).
    excluded_slugs: str = "binance-staked-eth,binance-staked-sol"

    # Max concurrent DefiLlama detail fetches during a monitoring pass.
    # The public API has no documented rate limit; keep this modest.
    crawl_concurrency: int = 8

    # Bound on the in-process per-protocol research cache (LRU). Keeps memory
    # flat on long-lived processes that discover the whole market.
    research_cache_max_entries: int = 256

    # --- Protocol discovery catalog (separate from monitoring) ---------------
    # The catalog is the full DefiLlama directory persisted to the DB, powering
    # the paginated /api/protocols explorer. None of these settings widen the
    # monitored watchlist or trigger a Dune/analytics crawl - discovery is
    # metadata only. The allowed page sizes are a fixed API contract, enforced by
    # the schemas.CatalogPageSize enum (and surfaced in OpenAPI), not config.
    # Longest search term accepted, so a stray paste cannot build a pathological
    # LIKE over the whole table.
    catalog_search_max_length: int = 120
    # Populate the catalog in the background on startup (best-effort, never a
    # blocking or analytics call). Disable to require an explicit sync.
    catalog_sync_on_startup: bool = True

    # --- Catalog pre-seed (DB-first detail warmth) ----------------------------
    # A bounded background crawl that persists snapshots for catalog protocols
    # the watchlist does not track, so detail pages are rich on first visit
    # instead of gap-only until someone views them. Rows are written
    # ``monitored = 0``: they serve detail reads but never enter dashboard
    # aggregates or the staleness clock. Disable for deployments that must not
    # add DefiLlama load (detail pages then fill on view via monitoring passes).
    preseed_enabled: bool = True
    # Protocols crawled per batch (through ``crawl_concurrency``), then a pause.
    preseed_batch_size: int = 150
    preseed_batch_pause_seconds: float = 90.0
    # A batch is crawled in chunks this size, pausing between them. One
    # 150-protocol gather plus its pandas parsing monopolises the single event
    # loop for seconds at a time, and interactive requests (login!) queue
    # behind it. Yielding per chunk keeps the API responsive while the seed
    # drains; the total crawl work is unchanged.
    preseed_chunk_size: int = 10
    preseed_chunk_pause_seconds: float = 0.5
    # Only seed protocols at or above this TVL first; the big names clear the
    # board-relevant majority long before the tail does.
    preseed_min_tvl: float = 1_000_000
    # After the floored queue drains, one final pass at floor 0 sweeps the rest
    # of the catalog. Heavier on the upstream - the honest knob to turn off.
    preseed_backfill_rest: bool = True

    # LLM (optional - template fallback is used when no key is configured)
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    # --- Ask-the-analyst RAG chat (roadmap #8) --------------------------------
    # Embeddings reuse the same OpenAI-compatible host/key as the brief LLM.
    # When no key is configured the retrieval degrades to a pure-Python BM25
    # lexical index and answers are composed extractively from quoted passages,
    # so the feature ships and works offline (the app's core differentiator).
    openai_embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    rag_enabled: bool = True
    # Number of chunks retrieved and fed to the model as numbered context.
    rag_top_k: int = 6
    # Target chunk size in characters (markdown is split on heading/paragraph
    # boundaries near this length; never mid-sentence at a hard cut).
    rag_chunk_size: int = 800
    # Relevance floor for the VECTOR (cosine) path, where scores live in [0, 1].
    # A chunk below this is not treated as supporting evidence.
    rag_min_score: float = 0.5
    # Relevance bar for the LEXICAL (BM25) path, whose scores are unbounded, so a
    # small absolute floor is meaningless (a single stray common word clears it).
    # Instead a passage must share at least this many *distinct informative query
    # terms* to count as supporting - tighten to reduce off-topic false matches,
    # loosen if terse single-term queries get refused. Capped by the query's own
    # informative-term count, so a one-word question still needs only one match.
    rag_min_query_term_overlap: int = 2
    # Generation style for the grounded LLM answer. Higher temperature + a
    # generous token budget yield fuller, more engaging prose; the honesty
    # guardrail (cite [n], state what cannot be established, never invent
    # numbers) is enforced by the system prompt, not by restraint here.
    rag_temperature: float = 0.5
    # Upper bound on answer length. Must be explicit because self-hosted
    # OpenAI-compatible servers (Ollama) otherwise truncate to a small default.
    rag_max_tokens: int = 1600
    # Per-request timeout for chat generation. Generous because a local CPU
    # model producing a long answer can exceed the default HTTP timeout; too low
    # a value makes the app needlessly degrade to the extractive fallback.
    rag_llm_timeout_seconds: float = 150.0
    # Browser-reachable WebSocket base for token streaming (WS /ws/chat). Empty
    # falls back to the HTTP API public URL's host with the ws/wss scheme.
    api_ws_url: str | None = None
    # Directory holding the methodology/architecture markdown the chat cites.
    # Empty auto-discovers the repo ``docs/`` (dev) or the image ``/app/docs``.
    rag_docs_dir: str | None = None

    # Alert thresholds
    alert_tvl_drop_pct: float = -15.0
    alert_tvl_surge_pct: float = 30.0
    alert_staking_ratio: float = 0.60
    alert_stale_data_days: int = 2
    # Depeg watch: alert when a protocol's own minted stablecoin drifts more
    # than this many basis points from its peg within the lookback window.
    # 50 bps = 0.5%; a USD coin trading at $0.995 or $1.005 crosses it.
    alert_depeg_bps: float = 50.0

    # --- Alert delivery (optional) -------------------------------------------
    # The monitoring pass always persists alerts; these settings control the
    # *fan-out* of new alerts to notification channels. The showcase runs with
    # no secrets: ``console`` always works and ``webhook`` activates only once a
    # URL is configured. Slack/Discord/Telegram/email stay dormant until their
    # env-backed secrets exist. Provider secrets are NEVER logged or persisted -
    # they are read here purely to open an outbound connection.
    alert_notify_enabled: bool = True
    alert_notify_channels: str = "console,webhook"
    # Alert ids are deterministic per protocol/rule/day, so a same-day re-run
    # would otherwise re-send. We also suppress re-notification within this
    # window (keyed on the alert id) so a still-firing alert re-alerts at most
    # once per cooldown. 360 min = at most a few nudges per day.
    alert_notify_cooldown_minutes: int = 360
    # Only deliver alerts at or above this severity: info | warning | critical.
    alert_notify_min_severity: str = "info"
    alert_notify_webhook_url: str | None = None
    # generic (full JSON body) | slack | discord (``{"text"/"content": ...}``).
    alert_notify_webhook_format: str = "generic"

    # Provider-specific config. A channel is only built when the values it needs
    # are all present; otherwise it is silently skipped (with a startup log).
    slack_webhook_url: str | None = None
    discord_webhook_url: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_starttls: bool = True
    smtp_from: str | None = None
    smtp_to: str | None = None

    @field_validator("dune_activity_query_id", mode="before")
    @classmethod
    def _blank_query_id_is_unset(cls, value: object) -> object:
        """Treat ``DEFISCOPE_DUNE_ACTIVITY_QUERY_ID=`` as "unset".

        An empty assignment is the idiomatic way to leave an optional key in a
        .env file; without this it would crash startup on int parsing rather
        than degrading to the documented "no on-chain data" state."""
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return value

    @property
    def onchain_ready(self) -> bool:
        """True only when on-chain data can actually be fetched.

        Every caller checks this instead of the individual fields, so "enabled
        but unconfigured" always resolves to the same, explicit data gap."""
        return bool(self.onchain_data_enabled and self.dune_api_key and self.dune_activity_query_id)

    @property
    def cache_ready(self) -> bool:
        """True only when the Redis catalog cache can actually be used.

        Mirrors ``onchain_ready``: every caller checks this, so "enabled but no
        URL" and "URL but disabled" both resolve to the same honest no-op where
        catalog reads are served straight from the database."""
        return bool(self.catalog_cache_enabled and (self.redis_url or "").strip())

    @property
    def protocol_slugs(self) -> list[str]:
        return [s.strip() for s in self.default_protocols.split(",") if s.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]

    @property
    def excluded_category_set(self) -> set[str]:
        return {s.strip() for s in self.excluded_categories.split(",") if s.strip()}

    @property
    def excluded_slug_set(self) -> set[str]:
        return {s.strip() for s in self.excluded_slugs.split(",") if s.strip()}

    @property
    def notify_channel_list(self) -> list[str]:
        return [c.strip().lower() for c in self.alert_notify_channels.split(",") if c.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
