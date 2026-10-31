from datetime import date
from io import BytesIO

from PIL import Image

from sws_membership.auth import service as auth
from sws_membership.auth.dependencies import SESSION_COOKIE
from sws_membership.catalog.router import current_day
from sws_membership.catalog.sample_data import load_sample_catalog
from sws_membership.members import photos
from sws_membership.members.member_numbers import allocate_member_number
from sws_membership.members.models import Member, MemberRole, MemberRoleAssignment, Sport
from sws_membership.storage.objects import LocalDirectoryStorage
from tests.conftest import sign_current_waiver

YEAR = 2026
TODAY = date(YEAR, 6, 15)


def jpeg(width=1200, height=800) -> bytes:
    out = BytesIO()
    Image.new("RGB", (width, height), (200, 120, 50)).save(out, "JPEG")
    return out.getvalue()


def _member(session, email="prof@example.com", roles=()) -> Member:
    member = Member(
        member_number=allocate_member_number(session),
        first_name="Pro",
        last_name="File",
        email=email,
        roles=[MemberRoleAssignment(role=r) for r in roles],
    )
    session.add(member)
    session.flush()
    return member


def _sign_in(session, client, member, storage=None):
    client.cookies.set(SESSION_COOKIE, auth.open_session(session, member))
    client.app.dependency_overrides[current_day] = lambda: TODAY
    if storage is not None:
        client.app.state.storage = storage


PROFILE = {
    "first_name": "Pro",
    "last_name": "File",
    "phone": "604-555-0100",
    "date_of_birth": "1990-01-01",
    "address_line_1": "1 Spit Road",
    "city": "Squamish",
    "province": "BC",
    "postal_code": "V8B 0A1",
    "sports": ["kite_foil", "wing"],
}


def test_photo_is_normalised_to_a_small_jpeg_without_metadata():
    data = photos.normalise_photo(jpeg(3000, 2000))
    image = Image.open(BytesIO(data))
    assert image.format == "JPEG" and max(image.size) == photos.PHOTO_SIZE
    assert not image.info.get("exif")


def test_non_images_and_oversized_uploads_are_rejected():
    for bad in (b"not an image", b"%PDF-1.4 fake"):
        try:
            photos.normalise_photo(bad)
        except photos.PhotoRejected:
            pass
        else:
            raise AssertionError("accepted a non-image")
    try:
        photos.normalise_photo(b"\xff" * (photos.MAX_UPLOAD_BYTES + 1))
    except photos.PhotoRejected as why:
        assert "larger" in str(why)


def test_profile_completes_through_the_api_and_unlocks_the_catalog(session, client, tmp_path):
    load_sample_catalog(session, YEAR)
    member = _member(session)
    sign_current_waiver(session, member)
    _sign_in(session, client, member, LocalDirectoryStorage(tmp_path / "store"))

    before = client.get("/api/me/profile").json()
    assert before["missing"] == ["photo", "date of birth", "address", "sports"]
    day_pass = next(
        p for p in client.get("/api/catalog").json() if p["name"].startswith("Day Pass")
    )
    assert day_pass["locked_because"] == ["Complete your profile: photo, address and sports"]

    updated = client.put("/api/me/profile", json=PROFILE).json()
    assert updated["missing"] == ["photo"]
    assert updated["sports"] == ["kite_foil", "wing"]

    uploaded = client.post(
        "/api/me/photo", files={"photo": ("me.jpg", jpeg(), "image/jpeg")}
    ).json()
    assert uploaded["missing"] == [] and uploaded["has_photo"] is True
    assert client.get("/api/me/photo").headers["content-type"] == "image/jpeg"

    day_pass = next(
        p for p in client.get("/api/catalog").json() if p["name"].startswith("Day Pass")
    )
    assert day_pass["purchasable"] is True

    card = client.get("/api/me/card.pdf")
    assert card.status_code == 200 and card.content.startswith(b"%PDF")


def test_birth_date_once_set_is_not_changed_by_the_member(session, client):
    member = _member(session)
    member.date_of_birth = date(1985, 5, 5)
    session.flush()
    _sign_in(session, client, member)
    response = client.put("/api/me/profile", json={**PROFILE, "date_of_birth": "1999-09-09"})
    assert response.status_code == 400
    assert (
        client.put("/api/me/profile", json={**PROFILE, "date_of_birth": "1985-05-05"}).status_code
        == 200
    )


def test_bad_uploads_are_refused_through_the_api(session, client, tmp_path):
    _sign_in(session, client, _member(session), LocalDirectoryStorage(tmp_path / "store"))
    response = client.post("/api/me/photo", files={"photo": ("x.txt", b"hello", "text/plain")})
    assert response.status_code == 400


def test_staff_can_photograph_a_member_at_the_kiosk(session, client, tmp_path):
    staff = _member(session, "staff@example.com", roles=[MemberRole.STAFF])
    member = _member(session, "walkin@example.com")
    _sign_in(session, client, staff, LocalDirectoryStorage(tmp_path / "store"))
    response = client.post(
        f"/api/staff/members/{member.id}/photo", files={"photo": ("m.jpg", jpeg(), "image/jpeg")}
    )
    assert response.status_code == 200 and response.json()["has_photo"] is True
    assert client.get(f"/api/staff/members/{member.id}/photo").status_code == 200
    assert member.photo_key.startswith(f"photos/{member.id}/")


def test_sports_list_is_the_closed_list(client):
    values = [s["value"] for s in client.get("/api/sports").json()]
    assert values == [sport.value for sport in Sport]
