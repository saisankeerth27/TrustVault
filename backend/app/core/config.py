from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables or a local .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "TrustVault API"
    app_version: str = "0.1.0"
    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    cors_allowed_origins: str = "http://localhost:5173"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def validate_cors_configuration(self) -> "Settings":
        origins = self.cors_origins

        if not origins:
            raise ValueError("CORS_ALLOWED_ORIGINS must contain at least one origin.")

        if "*" in origins and self.app_env != "development":
            raise ValueError("Wildcard CORS origins are only allowed in development.")

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
