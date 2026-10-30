"""Process configuration, read once from the environment."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SWS_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://sws:sws@localhost:5432/sws_membership"


settings = Settings()
