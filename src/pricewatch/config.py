from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="PRICEWATCH_",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8080
    database_url: str = "sqlite:///./data/pricewatch.db"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"

    # Full Good-search MCP URL including the secret path segment (Tailscale Funnel).
    # Example: https://your-host.tailXXXX.ts.net/mcp/<secret>
    good_search_mcp_url: str = ""
    good_search_auto_discover: bool = False
    good_search_mcp_url_candidates: str = ""
    good_search_scrape_tool: str = "scrape"
    good_search_search_url_template: str = "https://html.duckduckgo.com/html/?q={query}"
    good_search_max_chars: int = 20000
    good_search_max_tier: int = 2
    good_search_timeout_seconds: float = 120.0

    check_interval_minutes: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
