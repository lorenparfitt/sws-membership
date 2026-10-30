"""Wiring only: build the FastAPI application and mount the routers."""

from fastapi import FastAPI

from sws_membership.health import router as health_router


def create_application() -> FastAPI:
    application = FastAPI(title="SWS Membership")
    application.include_router(health_router)
    return application


application = create_application()
