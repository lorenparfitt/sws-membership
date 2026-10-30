"""Tests run against a real Postgres: the schema that ships, not a mock.

The suite creates the test database if it is missing, migrates it to head
once per run, and wraps every test in a transaction that is rolled back, so
tests never see each other's rows.
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from sws_membership.settings import settings

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _ensure_database_exists(url: str) -> None:
    target = make_url(url)
    maintenance = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with maintenance.connect() as connection:
        exists = connection.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": target.database}
        ).scalar()
        if not exists:
            connection.execute(text(f'CREATE DATABASE "{target.database}"'))
    maintenance.dispose()


def _migrate_to_head(url: str) -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")


@pytest.fixture(scope="session")
def engine():
    url = settings.test_database_url
    _ensure_database_exists(url)
    _migrate_to_head(url)
    engine = create_engine(url)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine):
    """A session inside one outer transaction that is always rolled back."""
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            yield session
        transaction.rollback()


class RecordingMailer:
    """Keeps every message so a test can read the link that was sent."""

    def __init__(self) -> None:
        self.sent: list = []

    def send(self, message) -> None:
        self.sent.append(message)


@pytest.fixture
def mailer():
    return RecordingMailer()


@pytest.fixture
def client(session, mailer):
    """An API client whose requests share the test's rolled-back session."""
    from fastapi.testclient import TestClient

    from sws_membership.auth.dependencies import get_database_session
    from sws_membership.main import create_application

    application = create_application(mailer=mailer)
    application.dependency_overrides[get_database_session] = lambda: session
    with TestClient(application) as client:
        yield client
