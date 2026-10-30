"""Wiring only: logging, the FastAPI application, and the mounted routers."""

import logging

from fastapi import FastAPI

from sws_membership.auth.router import router as auth_router
from sws_membership.catalog.router import router as catalog_router
from sws_membership.health import router as health_router
from sws_membership.mail.mailer import ConsoleMailer, Mailer
from sws_membership.settings import settings


def configure_logging() -> None:
    """Application loggers report at the configured level.

    The server configures only its own loggers; without this the root stays
    at WARNING and the console mailer's sign-in links never appear.
    """
    logging.basicConfig(level=settings.log_level, format="%(levelname)s %(name)s: %(message)s")


def create_application(mailer: Mailer | None = None) -> FastAPI:
    application = FastAPI(title="SWS Membership")
    application.state.mailer = mailer or ConsoleMailer()
    application.include_router(health_router)
    application.include_router(auth_router)
    application.include_router(catalog_router)
    return application


configure_logging()
application = create_application()
