import base64
import io
import struct
import zlib
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from sws_membership.auth import service as auth
from sws_membership.auth.dependencies import SESSION_COOKIE
from sws_membership.catalog.models import Product
from sws_membership.catalog.router import current_day
from sws_membership.catalog.sample_data import load_sample_catalog
from sws_membership.members.member_numbers import allocate_member_number
from sws_membership.members.models import Member, MemberRole, MemberRoleAssignment
from sws_membership.storage.objects import LocalDirectoryStorage
from sws_membership.waivers import service
from sws_membership.waivers.models import WaiverSignature

YEAR = 2026
TODAY = date(YEAR, 6, 15)
NOW = datetime(YEAR, 6, 15, 10, 0, tzinfo=UTC)


def tiny_png() -> bytes:
    """A valid 1x1 white PNG, built by hand so no image library is needed."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    raw = zlib.compress(b"\x00\xff\xff\xff")
    out = io.BytesIO()
    out.write(b"\x89PNG\r\n\x1a\n")
    out.write(chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)))
    out.write(chunk(b"IDAT", raw))
    out.write(chunk(b"IEND", b""))
    return out.getvalue()


def data_url(png: bytes = tiny_png()) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode()


def _member(session, email="signer@example.com", birth=date(1990, 1, 1), roles=()) -> Member:
    member = Member(
        member_number=allocate_member_number(session),
        first_name="Sig",
        last_name="Nature",
        email=email,
        date_of_birth=birth,
        roles=[MemberRoleAssignment(role=r) for r in roles],
    )
    session.add(member)
    session.flush()
    return member


@pytest.fixture
def storage(tmp_path):
    return LocalDirectoryStorage(tmp_path / "store")


@pytest.fixture
def template(session):
    return service.publish_template(session, "Waiver v1", "I accept the risks.", by=None, now=NOW)


def test_signing_the_current_template_counts_and_stores_the_image(session, storage, template):
    member = _member(session)
    row = service.sign(
        session,
        storage,
        member,
        template.id,
        service.SignatureInput("Sig Nature", data_url()),
        "1.2.3.4",
        now=NOW,
    )
    assert service.has_current_waiver(session, member)
    assert row.document_hash == service.document_hash("I accept the risks.")
    assert storage.get(row.signature_key) == tiny_png()
    assert row.guardian_name is None and row.guardian_signature_key is None


def test_a_new_version_makes_old_signatures_stale(session, storage, template):
    member = _member(session)
    service.sign(
        session,
        storage,
        member,
        template.id,
        service.SignatureInput("Sig", data_url()),
        "1.1.1.1",
        now=NOW,
    )
    service.publish_template(
        session, "Waiver v2", "New words.", by=None, now=NOW + timedelta(days=1)
    )
    assert not service.has_current_waiver(session, member)
    with pytest.raises(service.SignatureRejected):
        service.sign(
            session,
            storage,
            member,
            template.id,
            service.SignatureInput("Sig", data_url()),
            "1.1.1.1",
        )


def test_an_admin_reset_makes_signatures_stale_until_signed_again(session, storage, template):
    member = _member(session)
    service.sign(
        session,
        storage,
        member,
        template.id,
        service.SignatureInput("Sig", data_url()),
        "1.1.1.1",
        now=NOW,
    )
    service.reset_signatures(session, by=None, reason="Insurer asked", now=NOW + timedelta(hours=1))
    assert not service.has_current_waiver(session, member)
    service.sign(
        session,
        storage,
        member,
        template.id,
        service.SignatureInput("Sig", data_url()),
        "1.1.1.1",
        now=NOW + timedelta(hours=2),
    )
    assert service.has_current_waiver(session, member)
    assert session.scalar(
        select(WaiverSignature.id).where(WaiverSignature.member_id == member.id).limit(1)
    )


def test_minors_need_a_guardian_and_both_images_are_kept(session, storage, template):
    youth = _member(session, "youth@example.com", birth=date(YEAR - 15, 1, 1))
    with pytest.raises(service.SignatureRejected):
        service.sign(
            session,
            storage,
            youth,
            template.id,
            service.SignatureInput("Kid", data_url()),
            "1.1.1.1",
            now=NOW,
        )
    row = service.sign(
        session,
        storage,
        youth,
        template.id,
        service.SignatureInput(
            "Kid", data_url(), guardian_name="Parent", guardian_signature_png=data_url()
        ),
        "1.1.1.1",
        now=NOW,
    )
    assert row.guardian_name == "Parent"
    assert storage.get(row.guardian_signature_key) == tiny_png()


def test_unknown_birth_date_is_treated_as_a_minor(session):
    assert service.needs_guardian(Member(date_of_birth=None), TODAY)
    assert service.needs_guardian(Member(date_of_birth=date(YEAR - 19, 6, 16)), TODAY)
    assert not service.needs_guardian(Member(date_of_birth=date(YEAR - 19, 6, 15)), TODAY)


@pytest.mark.parametrize(
    "bad",
    [
        "not a data url",
        "data:image/png;base64,###",
        "data:image/png;base64," + base64.b64encode(b"GIF89a").decode(),
    ],
)
def test_signature_images_must_be_real_pngs(session, storage, template, bad):
    member = _member(session)
    with pytest.raises(service.SignatureRejected):
        service.sign(
            session, storage, member, template.id, service.SignatureInput("Sig", bad), "1.1.1.1"
        )


# --- through the API, and into the catalog gate ---------------------------


def _sign_in(session, client, member):
    client.cookies.set(SESSION_COOKIE, auth.open_session(session, member))
    client.app.dependency_overrides[current_day] = lambda: TODAY


def test_waiver_gates_the_day_pass_until_signed(session, client, storage, template):
    client.app.state.storage = storage
    load_sample_catalog(session, YEAR)
    member = _member(session)
    _sign_in(session, client, member)

    before = client.get("/api/waiver").json()
    assert (before["signed"], before["version"], before["needs_guardian"]) == (False, 1, False)
    day_pass = next(
        p for p in client.get("/api/catalog").json() if p["name"].startswith("Day Pass")
    )
    assert day_pass["locked_because"] == ["Sign the current waiver first"]
    assert client.post("/api/orders", json={"product_ids": [day_pass["id"]]}).status_code == 409

    signed = client.post(
        "/api/waiver/sign",
        json={"template_id": template.id, "signer_name": "Sig Nature", "signature_png": data_url()},
    )
    assert signed.status_code == 201, signed.text
    assert signed.json()["signed"] is True
    day_pass = next(
        p for p in client.get("/api/catalog").json() if p["name"].startswith("Day Pass")
    )
    assert day_pass["purchasable"] is True
    assert client.post("/api/orders", json={"product_ids": [day_pass["id"]]}).status_code == 201


def test_only_admins_publish_or_reset(session, client, template):
    member = _member(session, "plain@example.com")
    _sign_in(session, client, member)
    assert (
        client.post("/api/admin/waiver/publish", json={"title": "x", "body_text": "y"}).status_code
        == 403
    )
    assert client.post("/api/admin/waiver/reset", json={"reason": "r"}).status_code == 403

    admin = _member(session, "admin@example.com", roles=[MemberRole.ADMIN])
    _sign_in(session, client, admin)
    published = client.post(
        "/api/admin/waiver/publish", json={"title": "Waiver v2", "body_text": "New words."}
    )
    assert published.status_code == 201 and published.json()["version"] == 2
    assert client.post("/api/admin/waiver/reset", json={"reason": ""}).status_code == 400
    assert (
        client.post("/api/admin/waiver/reset", json={"reason": "Season start"}).status_code == 201
    )
    assert client.get("/api/waiver").json()["version"] == 2


def test_membership_alone_does_not_need_the_waiver(session, client, template):
    load_sample_catalog(session, YEAR)
    _sign_in(session, client, _member(session))
    products = {p["name"]: p for p in client.get("/api/catalog").json()}
    assert products[f"Adult SWS Membership {YEAR}"]["purchasable"] is True
    assert products[f"Adult Season Pass {YEAR}"]["locked_because"] == [
        "Sign the current waiver first"
    ]
    assert Product.__tablename__ == "products"
