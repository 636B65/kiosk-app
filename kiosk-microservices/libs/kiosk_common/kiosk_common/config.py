"""Configuration shared by every service (environment variables / .env)."""

import secrets
import sys

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_SECRET_LENGTH = 32


def _warn(message: str) -> None:
    print(f"[config] WARNING: {message}", file=sys.stderr, flush=True)


class ServiceConfig(BaseSettings):
    """Base settings. Each service subclasses this and sets ``service_name``.

    Secrets (``SECRET_KEY``, ``INTERNAL_TOKEN``) must be identical in every
    service; in Kubernetes they come from the ``kiosk-secrets`` Secret. When one
    is missing a random value is generated so a service never starts with a
    well-known key - but tokens then only validate within that one process.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "service"
    # SQLAlchemy URL; Postgres in Kubernetes, a SQLite file for local runs/tests.
    database_url: str = ""
    data_dir: str = "data"

    secret_key: str = ""
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480
    internal_token: str = ""

    auth_service_url: str = "http://auth-service:8000"
    catalog_service_url: str = "http://catalog-service:8000"
    customer_service_url: str = "http://customer-service:8000"
    order_service_url: str = "http://order-service:8000"
    settings_service_url: str = "http://settings-service:8000"
    audit_service_url: str = "http://audit-service:8000"
    report_service_url: str = "http://report-service:8000"
    system_service_url: str = "http://system-service:8000"

    cors_origins: str = ""
    upstream_timeout_seconds: float = 5.0
    outbox_interval_seconds: float = 2.0
    # Positive token verifications are cached this long (0 = verify every call).
    auth_cache_seconds: int = 60
    # Proxies in front of the service that append to X-Forwarded-For
    # (ingress controller + gateway = 2; docker compose gateway only = 1).
    trusted_proxies: int = 2

    @model_validator(mode="after")
    def _fill_defaults(self):
        if not self.database_url:
            self.database_url = f"sqlite:///{self.data_dir}/{self.service_name}.db"
        if not self.secret_key:
            _warn(
                "SECRET_KEY is not set; generated a random one, so admin tokens only "
                "work within this process. Set the same SECRET_KEY in every service."
            )
            self.secret_key = secrets.token_urlsafe(48)
        elif len(self.secret_key) < MIN_SECRET_LENGTH:
            _warn("SECRET_KEY is shorter than 32 characters; use e.g. `openssl rand -base64 48`.")
        if not self.internal_token:
            _warn(
                "INTERNAL_TOKEN is not set; generated a random one, so calls from other "
                "services will be rejected. Set the same INTERNAL_TOKEN in every service."
            )
            self.internal_token = secrets.token_urlsafe(48)
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        return origins or [
            "https://localhost",
            "http://localhost",
            "https://127.0.0.1",
            "http://127.0.0.1",
        ]
