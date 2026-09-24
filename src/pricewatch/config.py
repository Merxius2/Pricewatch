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

    good_search_base_url: str = "https://damngoodsearch.com/api/v1"
    good_search_api_key: str = ""

    check_interval_minutes: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
