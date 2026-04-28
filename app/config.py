from typing import List
from datetime import timedelta

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    SQLALCHEMY_DATABASE_URI: str = "sqlite:///profile.db"
    SECRET_KEY: str

    # JWT
    JWT_SECRET_KEY: str
    JWT_ACCESS_TOKEN_EXPIRES: timedelta | int = timedelta(minutes=3)
    JWT_REFRESH_TOKEN_EXPIRES: timedelta | int = timedelta(minutes=5)
    JWT_COOKIE_CSRF_PROTECT: bool = False
    JWT_TOKEN_LOCATION: List[str] = ["cookies"]

    # Logging
    DEBUG: bool = True
    LOG_FILE: str = ""

    # GitHub OAuth
    GITHUB_CLIENT_ID: str
    GITHUB_CLIENT_SECRET: str
    REDIRECT_URI: str

    # Redis
    REDIS_HOST: str
    REDIS_PORT: int
    REDIS_USERNAME: str
    REDIS_PASSWORD: str


settings = AppConfig()  # type: ignore
