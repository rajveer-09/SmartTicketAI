from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration comes from environment variables (or backend/.env)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_name: str = "SmartTicket API"
    environment: Literal["development", "test", "production"] = "development"
    frontend_url: str = "http://localhost:5173"

    # Database (Neon connection strings can be pasted as-is; see core/db_url.py)
    database_url: str = ""
    # Optional direct (non-pooled) endpoint for Alembic; falls back to database_url.
    migration_database_url: str = ""
    test_database_url: str = ""
    db_echo: bool = False

    # First admin
    admin_email: str = ""
    admin_password: str = ""
    admin_name: str = "Administrator"

    # Auth
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 14
    refresh_cookie_name: str = "refresh_token"
    refresh_cookie_secure: bool = False  # set true in production (HTTPS)
    refresh_cookie_samesite: Literal["lax", "strict", "none"] = "lax"

    # OTP
    otp_ttl_minutes: int = 10
    otp_max_attempts: int = 5
    otp_rate_limit_count: int = 3
    otp_rate_limit_window_minutes: int = 15

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/auth/google/callback"

    # AI (Phase 4)
    gemini_api_key: str = ""
    gemini_models: str = Field(default="", description="Comma-separated, strongest first")

    # Email (Phase 2/4)
    mail_username: str = ""
    mail_password: str = ""
    mail_from: str = ""
    mail_from_name: str = "SmartTicket"
    mail_server: str = "smtp.gmail.com"
    mail_port: int = 587

    # AI behaviour
    ai_timeout_seconds: int = 60
    model_backoff_minutes: int = 60  # how long a quota-exhausted model is skipped

    # Inngest
    inngest_dev: bool = True
    inngest_base_url: str = "http://127.0.0.1:8288"
    inngest_event_key: str = ""
    inngest_signing_key: str = ""

    @property
    def mail_enabled(self) -> bool:
        return bool(self.mail_username and self.mail_password and self.mail_from)

    @property
    def google_oauth_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @model_validator(mode="after")
    def _check_secrets(self) -> "Settings":
        if self.environment == "production" and len(self.jwt_secret) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters in production")
        return self

    @property
    def gemini_model_list(self) -> list[str]:
        return [m.strip() for m in self.gemini_models.split(",") if m.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
