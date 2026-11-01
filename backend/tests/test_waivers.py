import base64
import io
import struct
import zlib
from datetime import UTC, date, datetime, timedelta

import pytest

from sws_membership.catalog.sample_data import load_sample_catalog
from sws_membership.members.models import MemberRole
from sws_membership.waivers import service
from sws_membership.waivers.models import WaiverSignature
from tests.conftest import complete_profile, make_member

pytestmark = pytest.mark.django_db

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


def _member(email="signer@example.com", birth=date(1990, 1, 1), roles=()):
    return make_member(
        email, roles=roles, first_name="Sig", last_name="Nature", date_of_birth=birth
    )


@pytest.fixture
def template():
    return service.publish_template("Waiver v1", "I accept the risks.", by=None, now=NOW)


def _sign(storage, member, template, name="Sig", now=NOW, **extra):
    return service.sign(
        storage,
        member,
        template.id,
        service.SignatureInput(name, data_url(), **extra),
        "1.1.1.1",
        now=now,
    )


def test_signing_the_current_template_counts_and_stores_the_image(storage, template):
    member = _member()
    row = _sign(storage, member, template, "Sig Nature")
    assert service.has_current_waiver(member)
    assert row.document_hash == service.document_hash("I accept the risks.")
    assert storage.get(row.signature_key) == tiny_png()
    assert row.guardian_name is None and row.guardian_signature_key is None


def test_a_new_version_makes_old_signatures_stale(storage, template):
    member = _member()
    _sign(storage, member, template)
    service.publish_template("Waiver v2", "New words.", by=None, now=NOW + timedelta(days=1))
    assert not service.has_current_waiver(member)
    with pytest.raises(service.SignatureRejected):
        _sign(storage, member, template, now=None)


def test_an_admin_reset_makes_signatures_stale_until_signed_again(storage, template):
    member = _member()
    _sign(storage, member, template)
    service.reset_signatures(by=None, reason="Insurer asked", now=NOW + timedelta(hours=1))
    assert not service.has_current_waiver(member)
    _sign(storage, member, template, now=NOW + timedelta(hours=2))
    assert service.has_current_waiver(member)
    assert WaiverSignature.objects.filter(member=member).count() == 2


def test_minors_need_a_guardian_and_both_images_are_kept(storage, template):
    youth = _member("youth@example.com", birth=date(YEAR - 15, 1, 1))
    with pytest.raises(service.SignatureRejected):
        _sign(storage, youth, template, "Kid")
    row = _sign(
        storage, youth, template, "Kid", guardian_name="Parent", guardian_signature_png=data_url()
    )
    assert row.guardian_name == "Parent"
    assert storage.get(row.guardian_signature_key) == tiny_png()


def test_unknown_birth_date_is_treated_as_a_minor():
    assert service.needs_guardian(None, TODAY)
    assert service.needs_guardian(date(YEAR - 18, 6, 16), TODAY)
    assert not service.needs_guardian(date(YEAR - 18, 6, 15), TODAY)


@pytest.mark.parametrize(
    "bad",
    [
        "not a data url",
        "data:image/png;base64,###",
        "data:image/png;base64," + base64.b64encode(b"GIF89a").decode(),
    ],
)
def test_signature_images_must_be_real_pngs(storage, template, bad):
    member = _member()
    with pytest.raises(service.SignatureRejected):
        service.sign(storage, member, template.id, service.SignatureInput("Sig", bad), "1.1.1.1")


# --- through the API, and into the catalog gate ---------------------------


def test_waiver_gates_the_day_pass_until_signed(client, pin_today, template):
    load_sample_catalog(YEAR)
    member = _member()
    complete_profile(member)
    client.sign_in(member)
    pin_today(TODAY)

    before = client.get("/api/waiver").json()
    assert (before["signed"], before["version"], before["needs_guardian"]) == (False, 1, False)
    day_pass = next(
        p for p in client.get("/api/catalog").json() if p["name"].startswith("Day Pass")
    )
    assert day_pass["locked_because"] == ["Sign the current waiver first"]
    assert client.post_json("/api/orders", {"product_ids": [day_pass["id"]]}).status_code == 409

    signed = client.post_json(
        "/api/waiver/sign",
        {"template_id": template.id, "signer_name": "Sig Nature", "signature_png": data_url()},
    )
    assert signed.status_code == 201, signed.content
    assert signed.json()["signed"] is True
    day_pass = next(
        p for p in client.get("/api/catalog").json() if p["name"].startswith("Day Pass")
    )
    assert day_pass["purchasable"] is True
    assert client.post_json("/api/orders", {"product_ids": [day_pass["id"]]}).status_code == 201


def test_only_admins_publish_or_reset(client, template):
    client.sign_in(_member("plain@example.com"))
    assert (
        client.post_json("/api/admin/waiver/publish", {"title": "x", "body_text": "y"}).status_code
        == 403
    )
    assert client.post_json("/api/admin/waiver/reset", {"reason": "r"}).status_code == 403

    client.sign_in(_member("admin@example.com", roles=[MemberRole.ADMIN]))
    published = client.post_json(
        "/api/admin/waiver/publish", {"title": "Waiver v2", "body_text": "New words."}
    )
    assert published.status_code == 201 and published.json()["version"] == 2
    assert client.post_json("/api/admin/waiver/reset", {"reason": ""}).status_code == 400
    assert (
        client.post_json("/api/admin/waiver/reset", {"reason": "Season start"}).status_code == 201
    )
    assert client.get("/api/waiver").json()["version"] == 2


def test_membership_alone_does_not_need_the_waiver(client, pin_today, template):
    load_sample_catalog(YEAR)
    member = _member()
    complete_profile(member)
    client.sign_in(member)
    pin_today(TODAY)
    products = {p["name"]: p for p in client.get("/api/catalog").json()}
    assert products[f"Adult SWS Membership {YEAR}"]["purchasable"] is True
    assert products[f"Adult Season Pass {YEAR}"]["locked_because"] == [
        "Sign the current waiver first"
    ]
