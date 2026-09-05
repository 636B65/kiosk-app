import os
import secrets

from pydantic import field_validator
from pydantic_settings import BaseSettings


def _default_secret_key() -> str:
    """Generate a random secret on first import.

    Prefer setting SECRET_KEY in the environment (see docker-compose.yml).
    If none is set, a fresh random value is generated so the app no longer
    ships with a well-known signing key. A random value means tokens are
    invalidated on every restart - an acceptable trade-off versus using a
    publicly-known key that allows anyone to forge admin tokens.
    """
    return os.environ.get("SECRET_KEY") or secrets.token_urlsafe(48)


class Settings(BaseSettings):
    database_path: str = os.environ.get("DATABASE_PATH", "data/kiosk.db")
    secret_key: str = _default_secret_key()
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480

    @field_validator("secret_key")
    @classmethod
    def secret_key_not_empty(cls, v: str) -> str:
        # Docker Compose may pass SECRET_KEY="" when the host env var is
        # unset; never allow an empty signing key.
        return v or secrets.token_urlsafe(48)

    class Config:
        env_file = ".env"


settings = Settings()
