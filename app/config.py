from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuracion de la aplicacion. Todo valor puede sobreescribirse por variable de entorno."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://webauto:webauto@db:5432/webauto"

    redis_url: str = "redis://redis:6379/0"

    public_base_url: str = "http://localhost:8000"

    playwright_headless: bool = True
    playwright_timeout_ms: int = Field(default=15_000, ge=1_000)
    scraper_max_concurrency: int = Field(default=2, ge=1)

    saucedemo_username: str = "standard_user"
    saucedemo_password: str = "secret_sauce"

    log_level: str = "INFO"
    log_json: bool = True

    images_dir: Path = Path("storage/images")

    @property
    def images_base_url(self) -> str:
        return f"{self.public_base_url.rstrip('/')}/images"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
