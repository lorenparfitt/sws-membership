"""Wiring only: logging, the FastAPI application, and the mounted routers."""

import logging
from pathlib import Path

from fastapi import FastAPI

from sws_membership.auth.router import router as auth_router
from sws_membership.catalog.router import router as catalog_router
from sws_membership.entitlements.router import router as entitlements_router
from sws_membership.health import router as health_router
from sws_membership.kiosk.router import router as kiosk_router
from sws_membership.mail.mailer import ConsoleMailer, Mailer
from sws_membership.orders.router import router as orders_router
from sws_membership.payments.fake import FakeProcessor
from sws_membership.payments.fake_router import router as fake_payments_router
from sws_membership.payments.nuvei import NuveiProcessor
from sws_membership.payments.processor import PaymentProcessor
from sws_membership.settings import settings
from sws_membership.storage.objects import LocalDirectoryStorage, ObjectStorage
from sws_membership.waivers.router import router as waivers_router


def configure_logging() -> None:
    """Application loggers report at the configured level.

    The server configures only its own loggers; without this the root stays
    at WARNING and the console mailer's sign-in links never appear.
    """
    logging.basicConfig(level=settings.log_level, format="%(levelname)s %(name)s: %(message)s")


def configured_processor() -> PaymentProcessor:
    if settings.payment_processor == "nuvei":
        return NuveiProcessor(
            merchant_id=settings.nuvei_merchant_id,
            merchant_site_id=settings.nuvei_merchant_site_id,
            secret_key=settings.nuvei_secret_key,
            environment=settings.nuvei_environment,
            notification_url=settings.nuvei_notification_url,
        )
    return FakeProcessor()


def create_application(
    mailer: Mailer | None = None,
    payment_processor: PaymentProcessor | None = None,
    storage: ObjectStorage | None = None,
) -> FastAPI:
    application = FastAPI(title="SWS Membership")
    application.state.mailer = mailer or ConsoleMailer()
    application.state.storage = storage or LocalDirectoryStorage(Path(settings.storage_directory))
    application.state.payment_processor = payment_processor or configured_processor()
    application.include_router(health_router)
    application.include_router(auth_router)
    application.include_router(catalog_router)
    application.include_router(orders_router)
    application.include_router(entitlements_router)
    application.include_router(waivers_router)
    application.include_router(kiosk_router)
    if isinstance(application.state.payment_processor, FakeProcessor):
        application.include_router(fake_payments_router)
    return application


configure_logging()
application = create_application()
