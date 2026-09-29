import os
from pathlib import Path
from typing import Optional, Literal
from pydantic import field_validator
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

    @field_validator("DISCORD_TOKEN", mode="before")
    def clean_token(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip().strip("'\"")
        return v

    # Database Configuration
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/cpe_bot"

    # uHunt / UVa Settings
    UHUNT_BASE_URL: str = "https://uhunt.onlinejudge.org/api"
    UHUNT_TIMEOUT_SECONDS: float = 10.0

    # External UVa submission polling (all linked users)
    SUBMISSION_POLL_INTERVAL: int = 20  # seconds

    # Daily Problem Settings
    DAILY_REPEAT_COOLDOWN_DAYS: int = 30

    # Thread Settings
    AUTO_ARCHIVE_THREAD: bool = False

    # Logging
    LOG_LEVEL: str = "INFO"

    # Website / Judge integration (all optional; the Discord bot does not use these)
    WEBSITE_BASE_URL: str = "http://localhost:8000"
    WEBSITE_SESSION_SECRET: str = "change-this-session-secret"
    DISCORD_OAUTH_CLIENT_ID: str = ""
    DISCORD_OAUTH_CLIENT_SECRET: str = ""
    DISCORD_OAUTH_REDIRECT_URI: str = "http://localhost:8000/auth/callback"
    JUDGE0_URL: str = ""
    JUDGE0_API_KEY: str = ""
    JUDGE0_API_HOST: str = ""
    JUDGE0_TIMEOUT_SECONDS: float = 15.0
    JUDGE0_DEFAULT_MEMORY_LIMIT_KB: int = 262144
    APP_ENV: Literal["production", "development", "test"] = "production"
    JUDGE_PROVIDER: Literal["disabled", "mock", "judge0"] = "disabled"
    JUDGE_MOCK_VERDICT: Literal["ACCEPTED", "WRONG_ANSWER", "COMPILATION_ERROR", "TIME_LIMIT_EXCEEDED", "MEMORY_LIMIT_EXCEEDED", "RUNTIME_ERROR", "INTERNAL_ERROR"] = "ACCEPTED"
    JUDGE_MOCK_DELAY_SECONDS: float = 0.3

    model_config = SettingsConfigDict(
        env_file=get_default_env_file(),
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
