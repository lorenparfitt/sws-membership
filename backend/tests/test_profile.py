from datetime import date
from io import BytesIO

import pytest
from PIL import Image

from sws_membership.members import photos
from sws_membership.members.models import Member, MemberRole, Sport
from tests.conftest import make_member

pytestmark = pytest.mark.django_db


def jpeg(width=1200, height=800) -> bytes:
    out = BytesIO()
    Image.new("RGB", (width, height), (200, 120, 50)).save(out, "JPEG")
    return out.getvalue()


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
        with pytest.raises(photos.PhotoRejected):
            photos.normalise_photo(bad)
    with pytest.raises(photos.PhotoRejected, match="larger"):
        photos.normalise_photo(b"\xff" * (photos.MAX_UPLOAD_BYTES + 1))


def test_profile_fills_in_through_the_api(client):
    member = make_member("prof@example.com", first_name="Pro", last_name="File")
    client.sign_in(member)

    before = client.get("/api/me/profile").json()
    assert before["missing"] == ["photo", "date of birth", "address", "sports"]

    updated = client.put_json("/api/me/profile", PROFILE)
    assert updated.status_code == 200, updated.content
    assert updated.json()["missing"] == ["photo"]
    assert updated.json()["sports"] == ["kite_foil", "wing"]

    uploaded = client.post("/api/me/photo", {"photo": BytesIO(jpeg())})
    assert uploaded.status_code == 200, uploaded.content
    assert uploaded.json()["missing"] == [] and uploaded.json()["has_photo"] is True
    assert client.get("/api/me/photo").headers["content-type"] == "image/jpeg"
    assert Member.objects.get(id=member.id).profile_complete


def test_birth_date_once_set_is_not_changed_by_the_member(client):
    member = make_member("prof@example.com", date_of_birth=date(1985, 5, 5))
    client.sign_in(member)
    response = client.put_json("/api/me/profile", {**PROFILE, "date_of_birth": "1999-09-09"})
    assert response.status_code == 400
    assert (
        client.put_json("/api/me/profile", {**PROFILE, "date_of_birth": "1985-05-05"}).status_code
        == 200
    )


def test_bad_uploads_are_refused_through_the_api(client):
    client.sign_in(make_member("prof@example.com"))
    response = client.post("/api/me/photo", {"photo": BytesIO(b"hello")})
    assert response.status_code == 400


def test_staff_can_photograph_a_member_at_the_kiosk(client):
    staff = make_member("staff@example.com", roles=[MemberRole.STAFF])
    member = make_member("walkin@example.com")
    client.sign_in(staff)
    response = client.post(f"/api/staff/members/{member.id}/photo", {"photo": BytesIO(jpeg())})
    assert response.status_code == 200 and response.json()["has_photo"] is True
    assert client.get(f"/api/staff/members/{member.id}/photo").status_code == 200
    assert Member.objects.get(id=member.id).photo_key.startswith(f"photos/{member.id}/")


def test_sports_list_is_the_closed_list(client):
    values = [s["value"] for s in client.get("/api/sports").json()]
    assert values == [sport.value for sport in Sport]
