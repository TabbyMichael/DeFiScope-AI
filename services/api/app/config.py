"""Application settings loaded from environment / .env file."""

from functools import lru_cache

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

    # HTTP resilience: extra attempts (beyond the first) for transient
    # 429/5xx/transport errors when talking to DefiLlama. 0 disables retries.
    defillama_max_retries: int = 3

    # Persistence
    database_url: str = "sqlite:///./defiscope.db"

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
