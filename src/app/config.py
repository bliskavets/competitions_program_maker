"""Application settings loaded from environment / .env."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    secret_key: str = "dev-insecure-secret-change-me"
    database_url: str = "postgresql+psycopg2://sumo:sumo@db:5432/sumo"

    # Email
    email_backend: str = "console"  # "console" | "smtp"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@sumo.local"
    smtp_use_tls: bool = True

    page_size: int = 10

    # Session cookie
    session_cookie: str = "sumo_session"
    session_max_age: int = 60 * 60 * 24 * 14  # 14 days

    @property
    def sqlalchemy_url(self) -> str:
        """Normalise managed-host URLs (e.g. Render/Heroku give ``postgres://``)."""
        url = self.database_url
        if url.startswith("postgres://"):
            url = "postgresql+psycopg2://" + url[len("postgres://") :]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg2://" + url[len("postgresql://") :]
        return url


settings = Settings()
