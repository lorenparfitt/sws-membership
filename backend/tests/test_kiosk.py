from datetime import date

import pytest

from sws_membership.catalog.models import Product
from sws_membership.catalog.sample_data import load_sample_catalog
from sws_membership.entitlements.models import Entitlement, EntitlementKind
from sws_membership.kiosk import service
from sws_membership.kiosk.models import Station
from sws_membership.members.models import MemberRole
from tests.conftest import complete_profile, make_eligible, make_member, sign_current_waiver

pytestmark = pytest.mark.django_db

YEAR = 2026
TODAY = date(YEAR, 6, 15)
TOMORROW = date(YEAR, 6, 16)


def _member(email, first="Gate", last="Goer", number=None, roles=(), waiver=True):
    fields = {"first_name": first, "last_name": last, "date_of_birth": date(1990, 1, 1)}
    if number:
        fields["member_number"] = number
    member = make_member(email, roles=roles, **fields)
    if waiver:
        make_eligible(member)
    else:
        complete_profile(member)
    return member


def _grant(member, product_name, kind, visits=None) -> Entitlement:
    product = Product.objects.get(name=f"{product_name} {YEAR}")
    return Entitlement.objects.create(
        member=member,
        kind=kind,
        product=product,
        valid_from=date(YEAR, 1, 1),
        valid_to=date(YEAR, 12, 31),
        visits_remaining=visits,
    )


def test_search_by_scan_email_and_name():
    sam = _member("sam@example.com", "Sam", "Rider", number=4242)
    _member("pat@example.com", "Pat", "Ridley")
    assert service.search_members("00004242") == [sam]
    assert service.search_members("SWS-4242") == [sam]
    assert service.search_members(" Sam@Example.com ") == [sam]
    assert [m.last_name for m in service.search_members("rid")] == ["Rider", "Ridley"]
    assert service.search_members("sam rid") == [sam]
    assert service.search_members("999999") == []
    assert service.search_members("   ") == []


def test_season_pass_admits_without_spending_anything():
    load_sample_catalog(YEAR)
    staff = _member("staff@example.com", roles=[MemberRole.STAFF])
    member = _member("season@example.com")
    _grant(member, "Adult Season Pass", EntitlementKind.SEASON_ACCESS)
    day = _grant(member, "Day Pass", EntitlementKind.DAY_VISITS, visits=1)
    row, new = service.check_in(member, staff, Station.SPIT, TODAY)
    assert new and row.entitlement.kind == EntitlementKind.SEASON_ACCESS
    day.refresh_from_db()
    assert day.visits_remaining == 1


def test_day_pass_is_spent_once_per_day_then_runs_out():
    load_sample_catalog(YEAR)
    staff = _member("staff@example.com", roles=[MemberRole.STAFF])
    member = _member("day@example.com")
    day = _grant(member, "Day Pass", EntitlementKind.DAY_VISITS, visits=1)
    first, new = service.check_in(member, staff, Station.SPIT, TODAY)
    day.refresh_from_db()
    assert new and day.visits_remaining == 0
    again, new = service.check_in(member, staff, Station.SPIT, TODAY)
    day.refresh_from_db()
    assert not new and again == first and day.visits_remaining == 0
    with pytest.raises(service.CheckInRefused, match="no valid pass"):
        service.check_in(member, staff, Station.SPIT, TOMORROW)


def test_stations_admit_on_their_own_kinds():
    load_sample_catalog(YEAR)
    staff = _member("staff@example.com", roles=[MemberRole.STAFF])
    member = _member("shuttle@example.com")
    _grant(member, "Adult Season Pass", EntitlementKind.SEASON_ACCESS)
    with pytest.raises(service.CheckInRefused):
        service.check_in(member, staff, Station.SHUTTLE, TODAY)
    shuttle = _grant(member, "Member Day Shuttle Pass", EntitlementKind.SHUTTLE_ACCESS, visits=2)
    service.check_in(member, staff, Station.SHUTTLE, TODAY)
    shuttle.refresh_from_db()
    assert shuttle.visits_remaining == 1
    assert service.counts_for(TODAY) == {"spit": 0, "shuttle": 1}


def test_a_pass_that_needs_the_waiver_does_not_admit_without_it():
    load_sample_catalog(YEAR)
    staff = _member("staff@example.com", roles=[MemberRole.STAFF])
    member = _member("unsigned@example.com", waiver=False)
    _grant(member, "Day Pass", EntitlementKind.DAY_VISITS, visits=1)
    with pytest.raises(service.CheckInRefused, match="waiver"):
        service.check_in(member, staff, Station.SPIT, TODAY)
    sign_current_waiver(member)
    _, new = service.check_in(member, staff, Station.SPIT, TODAY)
    assert new


def test_kiosk_routes_are_staff_only(client):
    client.sign_in(_member("plain@example.com"))
    assert client.get("/api/staff/kiosk/lookup?q=1").status_code == 403
    assert (
        client.post_json(
            "/api/staff/kiosk/check-in", {"member_id": 1, "station": "spit"}
        ).status_code
        == 403
    )


def test_kiosk_lookup_and_check_in_through_the_api(client, pin_today):
    load_sample_catalog(YEAR)
    staff = _member("staff@example.com", roles=[MemberRole.STAFF])
    member = _member("scan@example.com", "Sam", "Rider", number=4242)
    _grant(member, "Day Pass", EntitlementKind.DAY_VISITS, visits=1)
    client.sign_in(staff)
    pin_today(TODAY)

    found = client.get("/api/staff/kiosk/lookup", {"q": "0004242"}).json()
    assert [m["member_number"] for m in found] == [4242]
    assert found[0]["waiver_current"] is True
    assert found[0]["passes"][0]["visits_remaining"] == 1
    assert found[0]["today"] == []

    result = client.post_json(
        "/api/staff/kiosk/check-in", {"member_id": member.id, "station": "spit"}
    ).json()
    assert (result["admitted"], result["new_today"]) == (True, True)
    assert result["member"]["passes"][0]["visits_remaining"] == 0
    assert result["member"]["today"][0]["station"] == "spit"

    again = client.post_json(
        "/api/staff/kiosk/check-in", {"member_id": member.id, "station": "spit"}
    ).json()
    assert (again["admitted"], again["new_today"]) == (True, False)
    assert client.get("/api/staff/kiosk/today").json() == {"spit": 1, "shuttle": 0}

    refused = client.post_json(
        "/api/staff/kiosk/check-in", {"member_id": member.id, "station": "shuttle"}
    ).json()
    assert refused["admitted"] is False and "no valid pass" in refused["message"]
