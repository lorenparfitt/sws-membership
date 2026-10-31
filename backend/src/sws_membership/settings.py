"""Process configuration, read once from the environment."""

from typing import Literal

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
    # Where signature images and card PDFs live in development. Production
    # swaps in object storage behind the same seam.
    storage_directory: str = "var/storage"
    # Printed on the back of every card as a QR code, as today.
    shuttle_url: str = "https://squamishwindsports.com/shuttle-boat-parking/"

    # Which processor charges cards. The fake one needs no network and is
    # approved by posting to the notification endpoint; production is nuvei.
    payment_processor: Literal["fake", "nuvei"] = "fake"
    nuvei_merchant_id: str = ""
    nuvei_merchant_site_id: str = ""
    nuvei_secret_key: str = ""
    nuvei_environment: Literal["int", "prod"] = "int"
    # Public URL Nuvei posts notifications to; must reach this API.
    nuvei_notification_url: str = "http://localhost:8000/api/payments/notification"


settings = Settings()
