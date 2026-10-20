from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, field_validator, model_validator
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
    database_url: str | None = None
    db_pool_size: int = 5
    db_max_overflow: int = 10

    jwt_secret: SecretStr | None = None
    jwt_algorithm: Literal["HS256"] = "HS256"
    jwt_issuer: str = "trustvault"
    jwt_audience: str = "trustvault-api"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    bcrypt_rounds: int = 12
    auth_cookie_secure: bool = False
    auth_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    auth_rate_limit_attempts: int = 10
    auth_rate_limit_window_seconds: int = 60

    @field_validator("database_url", mode="before")
    @classmethod
    def empty_database_url_to_none(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("jwt_access_token_expire_minutes", "jwt_refresh_token_expire_days")
    @classmethod
    def positive_token_lifetime(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Token lifetimes must be positive.")
        return value

    @field_validator("bcrypt_rounds")
    @classmethod
    def reasonable_bcrypt_cost(cls, value: int) -> int:
        if not 4 <= value <= 16:
            raise ValueError("BCRYPT_ROUNDS must be between 4 and 16.")
        return value

    @field_validator("auth_rate_limit_attempts", "auth_rate_limit_window_seconds")
    @classmethod
    def positive_rate_limit(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Authentication rate-limit settings must be positive.")
        return value

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def validate_security_configuration(self) -> "Settings":
        origins = self.cors_origins

        if not origins:
            raise ValueError("CORS_ALLOWED_ORIGINS must contain at least one origin.")

        if "*" in origins and self.app_env != "development":
            raise ValueError("Wildcard CORS origins are only allowed in development.")

        if self.auth_cookie_samesite == "none" and not self.auth_cookie_secure:
            raise ValueError("SameSite=None requires AUTH_COOKIE_SECURE=true.")

        if self.app_env == "production":
            secret = self.jwt_secret.get_secret_value() if self.jwt_secret else ""
            if len(secret) < 32:
                raise ValueError("JWT_SECRET must be at least 32 characters in production.")
            if not self.auth_cookie_secure:
                raise ValueError("AUTH_COOKIE_SECURE must be true in production.")

        return self

    def require_jwt_secret(self) -> str:
        if not self.jwt_secret:
            raise RuntimeError("JWT_SECRET is not configured.")
        return self.jwt_secret.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    return Settings()
