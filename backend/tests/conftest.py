"""Tests run against a real Postgres: the schema that ships, not a mock.

pytest-django creates the test database, applies the migrations once per
run, and wraps every test in a transaction that is rolled back. The three
seams (mail, storage, payments) are swapped for recording stand-ins.
"""

import json
from datetime import date

import pytest
from django.test import Client

from sws_membership.wiring import wiring


class RecordingMailer:
    """Keeps every message so a test can read the link that was sent."""

    def __init__(self) -> None:
        self.sent: list = []

    def send(self, message) -> None:
        self.sent.append(message)


@pytest.fixture(autouse=True)
def mailer():
    recording = RecordingMailer()
    wiring.mailer = recording
    yield recording
    wiring.mailer = None


@pytest.fixture(autouse=True)
def storage(tmp_path):
    from sws_membership.storage.objects import LocalDirectoryStorage

    local = LocalDirectoryStorage(tmp_path / "store")
    wiring.storage = local
    yield local
    wiring.storage = None


@pytest.fixture(autouse=True)
def processor():
    from sws_membership.payments.fake import FakeProcessor

    fake = FakeProcessor()
    wiring.processor = fake
    yield fake
    wiring.processor = None


class ApiClient(Client):
    """Django's test client with JSON bodies by default."""

    def _json(self, method, path, body, **extra):
        if body is None:
            return getattr(super(), method)(path, **extra)
        return getattr(super(), method)(
            path, data=json.dumps(body), content_type="application/json", **extra
        )

    def post_json(self, path, body=None, **extra):
        return self._json("post", path, body, **extra)

    def put_json(self, path, body=None, **extra):
        return self._json("put", path, body, **extra)

    def sign_in(self, member) -> None:
        self.force_login(member, backend="django.contrib.auth.backends.ModelBackend")


@pytest.fixture
def client():
    return ApiClient()


@pytest.fixture
def pin_today(monkeypatch):
    """Pin the calendar: pin_today(date(2026, 6, 15))."""
    from sws_membership import clock

    def pin(day: date) -> None:
        monkeypatch.setattr(clock, "today", lambda: day)

    return pin


def make_member(email="rider@example.com", roles=(), **fields):
    from sws_membership.members.member_numbers import allocate_member_number
    from sws_membership.members.models import Member, MemberRoleAssignment

    fields.setdefault("first_name", "Sam")
    fields.setdefault("last_name", "Rider")
    fields.setdefault("member_number", allocate_member_number())
    member = Member(email=email, **fields)
    member.set_unusable_password()
    member.save()
    MemberRoleAssignment.objects.bulk_create(
        MemberRoleAssignment(member=member, role=role) for role in roles
    )
    return member


def complete_profile(member) -> None:
    """Fill the fields the profile rule requires, with a fake photo key."""
    from sws_membership.members.models import MemberSport, Sport

    member.photo_key = member.photo_key or "test/photo.jpg"
    member.date_of_birth = member.date_of_birth or date(1990, 1, 1)
    member.address_line_1 = member.address_line_1 or "1 Spit Road"
    member.city = member.city or "Squamish"
    member.province = member.province or "BC"
    member.postal_code = member.postal_code or "V8B 0A1"
    member.save()
    if not member.sports.exists():
        MemberSport.objects.create(member=member, sport=Sport.KITE_TWIN_TIP)


def sign_current_waiver(member) -> None:
    """Give a test member a current signature, publishing a template if none exists.

    Writes the row directly: the signing path itself is covered in
    test_waivers.py, and other suites only need the gate open.
    """
    from django.utils import timezone

    from sws_membership.waivers import service
    from sws_membership.waivers.models import WaiverSignature

    template = service.current_template() or service.publish_template(
        "Test waiver", "Test waiver text.", by=None
    )
    WaiverSignature.objects.create(
        member=member,
        template=template,
        signed_at=timezone.now(),
        ip_address="test",
        signer_name=f"{member.first_name} {member.last_name}",
        signature_key="test/signature.png",
        document_hash=template.document_hash,
    )


def make_eligible(member) -> None:
    """A member who clears every non-product rule: complete profile and current waiver."""
    complete_profile(member)
    sign_current_waiver(member)
