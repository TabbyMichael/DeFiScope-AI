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

    # Protocols monitored by default (DefiLlama slugs)
    default_protocols: str = "aave-v3,uniswap-v3,lido,curve-dex,compound-v3"

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
