"""Process configuration, read once from the environment."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SWS_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://sws:sws@localhost:5432/sws_membership"
    # The test suite creates and migrates this database itself.
    test_database_url: str = "postgresql+psycopg://sws:sws@localhost:5432/sws_membership_test"
    # Where sign-in links point; the React app in development.
    frontend_base_url: str = "http://localhost:5173"
    # Off only for plain-http development. Production is https.
    cookie_secure: bool = False
    log_level: str = "INFO"


settings = Settings()
