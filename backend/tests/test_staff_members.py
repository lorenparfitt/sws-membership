from datetime import date

from sqlalchemy import select

from sws_membership.auth import service as auth
from sws_membership.auth.dependencies import SESSION_COOKIE
from sws_membership.catalog.models import Product
from sws_membership.catalog.router import current_day
from sws_membership.catalog.sample_data import load_sample_catalog
from sws_membership.members.member_numbers import allocate_member_number
from sws_membership.members.models import Member, MemberRole, MemberRoleAssignment
from tests.conftest import make_eligible

YEAR = 2026
TODAY = date(YEAR, 6, 15)


def _member(session, email, roles=(), birth=date(1990, 1, 1)) -> Member:
    member = Member(
        member_number=allocate_member_number(session),
        first_name="Walk",
        last_name="In",
        email=email,
        date_of_birth=birth,
        roles=[MemberRoleAssignment(role=r) for r in roles],
    )
    session.add(member)
    session.flush()
    return member


def _sign_in(session, client, member):
    client.cookies.set(SESSION_COOKIE, auth.open_session(session, member))
    client.app.dependency_overrides[current_day] = lambda: TODAY


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


def test_detail_shows_everything_the_counter_needs(session, client):
    load_sample_catalog(session, YEAR)
    staff = _member(session, "staff@example.com", roles=[MemberRole.STAFF])
    member = _member(session, "walkin@example.com")
    make_eligible(session, member)
    _sign_in(session, client, staff)

    detail = client.get(f"/api/staff/members/{member.id}").json()
    assert detail["member_number"] == member.member_number
    assert detail["waiver_current"] is True and detail["profile"]["missing"] == []
    assert detail["passes"] == [] and detail["orders"] == []
    names = {p["name"]: p for p in detail["catalog"]}
    assert names[f"Day Pass {YEAR}"]["purchasable"] is True

    day_pass = session.scalars(select(Product).where(Product.name == f"Day Pass {YEAR}")).one()
    sold = client.post(
        "/api/staff/orders",
        json={"member_id": member.id, "product_ids": [day_pass.id], "payment_method": "cash"},
    )
    assert sold.status_code == 201
    detail = client.get(f"/api/staff/members/{member.id}").json()
    assert [p["product_name"] for p in detail["passes"]] == [f"Day Pass {YEAR}"]
    assert (
        detail["orders"][0]["payment_method"] == "cash" and detail["orders"][0]["status"] == "paid"
    )


def test_staff_correct_birth_date_and_email_and_fix_the_profile(session, client):
    staff = _member(session, "staff@example.com", roles=[MemberRole.STAFF])
    member = _member(session, "old@example.com", birth=date(1990, 1, 1))
    _sign_in(session, client, staff)
    detail = client.put(f"/api/staff/members/{member.id}/profile", json=BODY).json()
    assert detail["profile"]["email"] == "walkin@example.com"
    assert detail["profile"]["date_of_birth"] == "1991-02-03"
    assert detail["profile"]["sports"] == ["windsurf"]
    assert detail["profile"]["missing"] == ["photo"]


def test_email_clash_and_future_birth_date_are_refused(session, client):
    staff = _member(session, "staff@example.com", roles=[MemberRole.STAFF])
    _member(session, "taken@example.com")
    member = _member(session, "me@example.com")
    _sign_in(session, client, staff)
    assert (
        client.put(
            f"/api/staff/members/{member.id}/profile", json={**BODY, "email": "taken@example.com"}
        ).status_code
        == 409
    )
    assert (
        client.put(
            f"/api/staff/members/{member.id}/profile", json={**BODY, "date_of_birth": "2099-01-01"}
        ).status_code
        == 400
    )
    assert client.get("/api/staff/members/999999").status_code == 404


def test_only_admins_change_roles(session, client):
    staff = _member(session, "staff@example.com", roles=[MemberRole.STAFF])
    admin = _member(session, "admin@example.com", roles=[MemberRole.ADMIN])
    member = _member(session, "promote@example.com")
    _sign_in(session, client, staff)
    assert (
        client.put(f"/api/staff/members/{member.id}/roles", json={"roles": ["staff"]}).status_code
        == 403
    )
    _sign_in(session, client, admin)
    detail = client.put(f"/api/staff/members/{member.id}/roles", json={"roles": ["staff"]}).json()
    assert detail["roles"] == ["staff"]
    detail = client.put(f"/api/staff/members/{member.id}/roles", json={"roles": []}).json()
    assert detail["roles"] == []


def test_plain_members_cannot_see_staff_detail(session, client):
    member = _member(session, "plain@example.com")
    _sign_in(session, client, member)
    assert client.get(f"/api/staff/members/{member.id}").status_code == 403
