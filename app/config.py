from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://webauto:webauto@db:5432/webauto"
    playwright_headless: bool = True

    class Config:
        env_file = ".env"

settings = Settings()
