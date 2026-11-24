"""12-factor settings loaded from the environment (and `.env` in local dev)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Role = Literal["api", "gateway", "worker"]
ALL_ROLES: list[Role] = ["api", "gateway", "worker"]

# Repo-root .env first, then backend/.env (later files win).
_ROOT = Path(__file__).resolve().parents[4]
_ENV_FILES = (_ROOT / ".env", _ROOT / "backend" / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILES, extra="ignore")

    # Runtime
    app_env: Literal["local", "test", "production"] = "local"
    app_roles: Annotated[list[Role], NoDecode] = Field(default_factory=lambda: list(ALL_ROLES))
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["http://localhost:3000"])
    log_level: str = "INFO"

    # Persistence
    database_url: str = "postgresql+asyncpg://hinglish:hinglish@localhost:5432/hinglish"

    # Adapter backends (Stage 0 = memory; Stage 1+ = redis)
    queue_backend: Literal["memory", "redis"] = "memory"
    rate_limit_backend: Literal["memory", "redis"] = "memory"
    redis_url: str | None = None

    # AI vendors (API-only; no models hosted here)
    sarvam_api_key: SecretStr | None = None
    sarvam_stt_model: str = "saaras:v4"
    sarvam_tts_model: str = "bulbul:v4-flash"
    groq_api_key: SecretStr | None = None
    groq_model: str = "openai/gpt-oss-20b"

    # Feature flags / policy
    enable_sarvam: bool = True
    enable_tts: bool = True
    use_fake_recognizer: bool = False
    max_session_seconds: int = 600
    review_passcode: SecretStr | None = None

    @field_validator("app_roles", "cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
