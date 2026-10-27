"""Application settings loaded from environment / .env file."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="DEFISCOPE_", extra="ignore")

    # Data sources
    defillama_base_url: str = "https://api.llama.fi"
    http_timeout_seconds: float = 30.0

    # Persistence
    database_url: str = "sqlite:///./defiscope.db"

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

    # LLM (optional - template fallback is used when no key is configured)
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    # Alert thresholds
    alert_tvl_drop_pct: float = -15.0
    alert_tvl_surge_pct: float = 30.0
    alert_staking_ratio: float = 0.60
    alert_stale_data_days: int = 2

    @property
    def protocol_slugs(self) -> list[str]:
        return [s.strip() for s in self.default_protocols.split(",") if s.strip()]

    @property
    def excluded_category_set(self) -> set[str]:
        return {s.strip() for s in self.excluded_categories.split(",") if s.strip()}

    @property
    def excluded_slug_set(self) -> set[str]:
        return {s.strip() for s in self.excluded_slugs.split(",") if s.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
