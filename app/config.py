from typing import List
from datetime import timedelta

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    SQLALCHEMY_DATABASE_URI: str = "sqlite:///profile.db"
    SECRET_KEY: str
    JWT_SECRET_KEY: str
    JWT_ACCESS_TOKEN_EXPIRES: timedelta = timedelta(minutes=3)
    JWT_REFRESH_TOKEN_EXPIRES: timedelta = timedelta(minutes=5)
    JWT_COOKIE_CSRF_PROTECT: bool = True
    JWT_TOKEN_LOCATION: List[str] = ["cookies"]

    # Logging
    DEBUG: bool = True
    LOG_FILE: str

    # GitHub OAuth
    GITHUB_CLIENT_ID: str
    GITHUB_CLIENT_SECRET: str
    REDIRECT_URI: str


settings = AppConfig()  # type: ignore
