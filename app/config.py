import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


def get_default_env_file() -> str:
    """Determine the env file location.

    Checks ENV_FILE env var, then /etc/discord-cpe/.env, then fallback to local .env.
    """
    if os.getenv("ENV_FILE"):
        return os.getenv("ENV_FILE")
    if Path("/etc/discord-cpe/.env").exists():
        return "/etc/discord-cpe/.env"
    return ".env"


class Settings(BaseSettings):
    # Discord Configuration
    DISCORD_TOKEN: str = ""

    # Database Configuration
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/cpe_bot"

    # uHunt / UVa Settings
    UHUNT_BASE_URL: str = "https://uhunt.onlinejudge.org/api"
    UHUNT_TIMEOUT_SECONDS: float = 10.0

    # Polling & Sessions
    SUBMISSION_POLL_INTERVAL: int = 20  # seconds

    # Daily Problem Settings
    DAILY_REPEAT_COOLDOWN_DAYS: int = 30

    # Thread Settings
    AUTO_ARCHIVE_THREAD: bool = False

    # Logging
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=get_default_env_file(),
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
