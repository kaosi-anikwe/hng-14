from pydantic_settings import BaseSettings, SettingsConfigDict

class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    SQLALCHEMY_DATABASE_URI: str = "sqlite:///profile.db"

    # Logging
    DEBUG: bool = True
    LOG_FILE: str

    # GitHub OAuth
    GITHUB_CLIENT_ID: str
    GITHUB_CLIENT_SECRET: str



settings = AppConfig() # type: ignore
