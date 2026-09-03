import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_path: str = os.environ.get("DATABASE_PATH", "data/kiosk.db")
    secret_key: str = os.environ.get("SECRET_KEY", "change-me-in-production")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480

    class Config:
        env_file = ".env"


settings = Settings()
