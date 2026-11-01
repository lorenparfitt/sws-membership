from datetime import date

import pytest

from sws_membership.catalog.models import Product
from sws_membership.catalog.sample_data import load_sample_catalog
from sws_membership.members.models import MemberRole
from tests.conftest import make_eligible, make_member

pytestmark = pytest.mark.django_db

YEAR = 2026
TODAY = date(YEAR, 6, 15)


def _member(email, roles=(), birth=date(1990, 1, 1)):
    return make_member(email, roles=roles, first_name="Walk", last_name="In", date_of_birth=birth)


BODY = {
    "first_name": "Walk",
    "last_name": "In",
    "email": "walkin@example.com",
    "phone": "604-555-0123",
    "date_of_birth": "1991-02-03",
    "address_line_1": "2 Spit Road",
    "city": "Squamish",
    "province": "BC",
    "postal_code": "V8B 0A2",
    "sports": ["windsurf"],
}


def test_detail_shows_everything_the_counter_needs(client, pin_today):
    load_sample_catalog(YEAR)
    pin_today(TODAY)
    staff = _member("staff@example.com", roles=[MemberRole.STAFF])
    member = _member("walkin@example.com")
    make_eligible(member)
    client.sign_in(staff)

    detail = client.get(f"/api/staff/members/{member.id}").json()
    assert detail["member_number"] == member.member_number
    assert detail["waiver_current"] is True and detail["profile"]["missing"] == []
    assert detail["passes"] == [] and detail["orders"] == []
    names = {p["name"]: p for p in detail["catalog"]}
    assert names[f"Day Pass {YEAR}"]["purchasable"] is True

    day_pass = Product.objects.get(name=f"Day Pass {YEAR}")
    sold = client.post_json(
        "/api/staff/orders",
        {"member_id": member.id, "product_ids": [day_pass.id], "payment_method": "cash"},
    )
    assert sold.status_code == 201
    detail = client.get(f"/api/staff/members/{member.id}").json()
    assert [p["product_name"] for p in detail["passes"]] == [f"Day Pass {YEAR}"]
    assert (
        detail["orders"][0]["payment_method"] == "cash" and detail["orders"][0]["status"] == "paid"
    )


def test_staff_correct_birth_date_and_email_and_fix_the_profile(client, pin_today):
    pin_today(TODAY)
    staff = _member("staff@example.com", roles=[MemberRole.STAFF])
    member = _member("old@example.com", birth=date(1990, 1, 1))
    client.sign_in(staff)
    response = client.put_json(f"/api/staff/members/{member.id}/profile", BODY)
    assert response.status_code == 200, response.content
    detail = response.json()
    assert detail["profile"]["email"] == "walkin@example.com"
    assert detail["profile"]["date_of_birth"] == "1991-02-03"
    assert detail["profile"]["sports"] == ["windsurf"]
    assert detail["profile"]["missing"] == ["photo"]


def test_email_clash_and_future_birth_date_are_refused(client, pin_today):
    pin_today(TODAY)
    staff = _member("staff@example.com", roles=[MemberRole.STAFF])
    _member("taken@example.com")
    member = _member("me@example.com")
    client.sign_in(staff)
    assert (
        client.put_json(
            f"/api/staff/members/{member.id}/profile", {**BODY, "email": "taken@example.com"}
        ).status_code
        == 409
    )
    assert (
        client.put_json(
            f"/api/staff/members/{member.id}/profile", {**BODY, "date_of_birth": "2099-01-01"}
        ).status_code
        == 400
    )
    assert client.get("/api/staff/members/999999").status_code == 404


def test_only_admins_change_roles(client):
    staff = _member("staff@example.com", roles=[MemberRole.STAFF])
    admin = _member("admin@example.com", roles=[MemberRole.ADMIN])
    member = _member("promote@example.com")
    client.sign_in(staff)
    assert (
        client.put_json(f"/api/staff/members/{member.id}/roles", {"roles": ["staff"]}).status_code
        == 403
    )
    client.sign_in(admin)
    detail = client.put_json(f"/api/staff/members/{member.id}/roles", {"roles": ["staff"]}).json()
    assert detail["roles"] == ["staff"]
    detail = client.put_json(f"/api/staff/members/{member.id}/roles", {"roles": []}).json()
    assert detail["roles"] == []


def test_plain_members_cannot_see_staff_detail(client):
    member = _member("plain@example.com")
    client.sign_in(member)
    assert client.get(f"/api/staff/members/{member.id}").status_code == 403
