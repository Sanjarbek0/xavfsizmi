"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Top-level settings; values come from process env / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Literal["development", "test", "staging", "production"] = "development"
    log_level: str = "INFO"
    brand_name: str = "Xavfsizmi"

    database_url: str = "postgresql+asyncpg://xavfsizmi:xavfsizmi_dev@localhost:5432/xavfsizmi"
    redis_url: str = "redis://localhost:6379/0"

    hibp_api_key: str = ""
    hibp_base_url: str = "https://haveibeenpwned.com/api/v3"
    hibp_user_agent: str = "xavfsizmi/0.1"

    turnstile_site_key: str = ""
    turnstile_secret_key: str = ""

    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "Xavfsizmi <noreply@xavfsizmi.example>"
    smtp_tls: bool = False

    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    session_secret: str = "please-change-me-in-production"
    allowed_origins: str = "http://localhost:5173"
    admin_emails: str = ""

    rl_lookup_per_ip: int = Field(default=20, ge=1)
    rl_api_free: int = Field(default=10, ge=1)
    rl_api_pro: int = Field(default=100, ge=1)
    rl_api_high_rpm: int = Field(default=600, ge=1)

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def admin_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
