from datetime import date

from sqlalchemy import select

from sws_membership.auth import service as auth
from sws_membership.auth.dependencies import SESSION_COOKIE
from sws_membership.catalog.models import Product
from sws_membership.catalog.router import current_day
from sws_membership.catalog.sample_data import load_sample_catalog
from sws_membership.entitlements.models import Entitlement, EntitlementKind
from sws_membership.kiosk import service
from sws_membership.kiosk.models import Station
from sws_membership.members.member_numbers import allocate_member_number
from sws_membership.members.models import Member, MemberRole, MemberRoleAssignment
from tests.conftest import make_eligible, sign_current_waiver

YEAR = 2026
TODAY = date(YEAR, 6, 15)
TOMORROW = date(YEAR, 6, 16)


def _member(
    session, email, first="Gate", last="Goer", number=None, roles=(), waiver=True
) -> Member:
    member = Member(
        member_number=number or allocate_member_number(session),
        first_name=first,
        last_name=last,
        email=email,
        date_of_birth=date(1990, 1, 1),
        roles=[MemberRoleAssignment(role=r) for r in roles],
    )
    session.add(member)
    session.flush()
    if waiver:
        make_eligible(session, member)
    else:
        from tests.conftest import complete_profile

        complete_profile(session, member)
    return member


def _grant(session, member, product_name, kind, visits=None) -> Entitlement:
    product = session.scalars(select(Product).where(Product.name == f"{product_name} {YEAR}")).one()
    row = Entitlement(
        member_id=member.id,
        kind=kind,
        product_id=product.id,
        valid_from=date(YEAR, 1, 1),
        valid_to=date(YEAR, 12, 31),
        visits_remaining=visits,
    )
    session.add(row)
    session.flush()
    return row


def test_search_by_scan_email_and_name(session):
    sam = _member(session, "sam@example.com", "Sam", "Rider", number=4242)
    _member(session, "pat@example.com", "Pat", "Ridley")
    assert service.search_members(session, "00004242") == [sam]
    assert service.search_members(session, "SWS-4242") == [sam]
    assert service.search_members(session, " Sam@Example.com ") == [sam]
    assert [m.last_name for m in service.search_members(session, "rid")] == ["Rider", "Ridley"]
    assert service.search_members(session, "sam rid") == [sam]
    assert service.search_members(session, "999999") == []
    assert service.search_members(session, "   ") == []


def test_season_pass_admits_without_spending_anything(session):
    load_sample_catalog(session, YEAR)
    staff = _member(session, "staff@example.com", roles=[MemberRole.STAFF])
    member = _member(session, "season@example.com")
    _grant(session, member, "Adult Season Pass", EntitlementKind.SEASON_ACCESS)
    day = _grant(session, member, "Day Pass", EntitlementKind.DAY_VISITS, visits=1)
    row, new = service.check_in(session, member, staff, Station.SPIT, TODAY)
    assert new and row.entitlement.kind is EntitlementKind.SEASON_ACCESS
    assert day.visits_remaining == 1


def test_day_pass_is_spent_once_per_day_then_runs_out(session):
    load_sample_catalog(session, YEAR)
    staff = _member(session, "staff@example.com", roles=[MemberRole.STAFF])
    member = _member(session, "day@example.com")
    day = _grant(session, member, "Day Pass", EntitlementKind.DAY_VISITS, visits=1)
    first, new = service.check_in(session, member, staff, Station.SPIT, TODAY)
    assert new and day.visits_remaining == 0
    again, new = service.check_in(session, member, staff, Station.SPIT, TODAY)
    assert not new and again is first and day.visits_remaining == 0
    try:
        service.check_in(session, member, staff, Station.SPIT, TOMORROW)
    except service.CheckInRefused as why:
        assert "no valid pass" in str(why)
    else:
        raise AssertionError("a spent day pass admitted again")


def test_stations_admit_on_their_own_kinds(session):
    load_sample_catalog(session, YEAR)
    staff = _member(session, "staff@example.com", roles=[MemberRole.STAFF])
    member = _member(session, "shuttle@example.com")
    _grant(session, member, "Adult Season Pass", EntitlementKind.SEASON_ACCESS)
    try:
        service.check_in(session, member, staff, Station.SHUTTLE, TODAY)
    except service.CheckInRefused:
        pass
    else:
        raise AssertionError("a season pass admitted to the shuttle")
    shuttle = _grant(
        session, member, "Member Day Shuttle Pass", EntitlementKind.SHUTTLE_ACCESS, visits=2
    )
    service.check_in(session, member, staff, Station.SHUTTLE, TODAY)
    assert shuttle.visits_remaining == 1
    assert service.counts_for(session, TODAY) == {"spit": 0, "shuttle": 1}


def test_a_pass_that_needs_the_waiver_does_not_admit_without_it(session):
    load_sample_catalog(session, YEAR)
    staff = _member(session, "staff@example.com", roles=[MemberRole.STAFF])
    member = _member(session, "unsigned@example.com", waiver=False)
    _grant(session, member, "Day Pass", EntitlementKind.DAY_VISITS, visits=1)
    try:
        service.check_in(session, member, staff, Station.SPIT, TODAY)
    except service.CheckInRefused as why:
        assert "waiver" in str(why)
    else:
        raise AssertionError("admitted without a waiver")
    sign_current_waiver(session, member)
    _, new = service.check_in(session, member, staff, Station.SPIT, TODAY)
    assert new


def _sign_in(session, client, member):
    client.cookies.set(SESSION_COOKIE, auth.open_session(session, member))
    client.app.dependency_overrides[current_day] = lambda: TODAY


def test_kiosk_routes_are_staff_only(session, client):
    _sign_in(session, client, _member(session, "plain@example.com"))
    assert client.get("/api/staff/kiosk/lookup?q=1").status_code == 403
    assert (
        client.post(
            "/api/staff/kiosk/check-in", json={"member_id": 1, "station": "spit"}
        ).status_code
        == 403
    )


def test_kiosk_lookup_and_check_in_through_the_api(session, client):
    load_sample_catalog(session, YEAR)
    staff = _member(session, "staff@example.com", roles=[MemberRole.STAFF])
    member = _member(session, "scan@example.com", "Sam", "Rider", number=4242)
    _grant(session, member, "Day Pass", EntitlementKind.DAY_VISITS, visits=1)
    _sign_in(session, client, staff)

    found = client.get("/api/staff/kiosk/lookup", params={"q": "0004242"}).json()
    assert [m["member_number"] for m in found] == [4242]
    assert found[0]["waiver_current"] is True
    assert found[0]["passes"][0]["visits_remaining"] == 1
    assert found[0]["today"] == []

    result = client.post(
        "/api/staff/kiosk/check-in", json={"member_id": member.id, "station": "spit"}
    ).json()
    assert (result["admitted"], result["new_today"]) == (True, True)
    assert result["member"]["passes"][0]["visits_remaining"] == 0
    assert result["member"]["today"][0]["station"] == "spit"

    again = client.post(
        "/api/staff/kiosk/check-in", json={"member_id": member.id, "station": "spit"}
    ).json()
    assert (again["admitted"], again["new_today"]) == (True, False)
    assert client.get("/api/staff/kiosk/today").json() == {"spit": 1, "shuttle": 0}

    refused = client.post(
        "/api/staff/kiosk/check-in", json={"member_id": member.id, "station": "shuttle"}
    ).json()
    assert refused["admitted"] is False and "no valid pass" in refused["message"]
