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

    good_search_mcp_url: str = "http://127.0.0.1:8765/mcp"
    good_search_search_tool: str = ""
    good_search_fetch_tool: str = ""
    good_search_timeout_seconds: float = 120.0

    check_interval_minutes: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
