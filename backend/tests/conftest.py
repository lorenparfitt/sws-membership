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


def sign_current_waiver(session, member) -> None:
    """Give a test member a current signature, publishing a template if none exists.

    Writes the row directly: the signing path itself is covered in
    test_waivers.py, and other suites only need the gate open.
    """
    from datetime import UTC, datetime

    from sws_membership.waivers import service
    from sws_membership.waivers.models import WaiverSignature

    template = service.current_template(session) or service.publish_template(
        session, "Test waiver", "Test waiver text.", by=None
    )
    session.add(
        WaiverSignature(
            member_id=member.id,
            template_id=template.id,
            signed_at=datetime.now(UTC),
            ip_address="test",
            signer_name=f"{member.first_name} {member.last_name}",
            signature_key="test/signature.png",
            document_hash=template.document_hash,
        )
    )
    session.flush()


def complete_profile(session, member) -> None:
    """Fill the fields the profile rule requires, with a fake photo key."""
    from datetime import date

    from sws_membership.members.models import MemberSport, Sport

    member.photo_key = member.photo_key or "test/photo.jpg"
    member.date_of_birth = member.date_of_birth or date(1990, 1, 1)
    member.address_line_1 = member.address_line_1 or "1 Spit Road"
    member.city = member.city or "Squamish"
    member.province = member.province or "BC"
    member.postal_code = member.postal_code or "V8B 0A1"
    if not member.sports:
        member.sports.append(MemberSport(sport=Sport.KITE_TWIN_TIP))
    session.flush()


def make_eligible(session, member) -> None:
    """A member who clears every non-product rule: complete profile and current waiver."""
    complete_profile(session, member)
    sign_current_waiver(session, member)
