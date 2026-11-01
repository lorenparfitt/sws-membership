from datetime import date

import pytest

from sws_membership.catalog.models import Product
from sws_membership.catalog.sample_data import load_sample_catalog
from sws_membership.members.models import MemberRole
from sws_membership.orders import service as orders
from sws_membership.orders.models import PaymentMethod
from tests.conftest import make_eligible, make_member

pytestmark = pytest.mark.django_db

YEAR = 2026
TODAY = date(YEAR, 6, 15)


def _admin(client, pin_today):
    admin = make_member(
        "admin@example.com", roles=[MemberRole.ADMIN], first_name="Ad", last_name="Min"
    )
    client.sign_in(admin)
    pin_today(TODAY)
    return admin


def _buyer(email, first, last):
    buyer = make_member(email, first_name=first, last_name=last, date_of_birth=date(1990, 1, 1))
    make_eligible(buyer)
    return buyer


def test_admin_routes_are_admin_only(client):
    client.sign_in(make_member("staff@example.com", roles=[MemberRole.STAFF]))
    assert client.get("/api/admin/catalog/products").status_code == 403
    assert client.get("/api/admin/reports").status_code == 403


def test_build_a_gated_product_from_nothing(client, pin_today):
    _admin(client, pin_today)
    created = client.post_json(
        "/api/admin/catalog/products",
        {
            "name": "Foil Clinic 2026",
            "description": "One evening.",
            "season_year": YEAR,
            "sort_order": 70,
        },
    )
    assert created.status_code == 201, created.content
    pid = created.json()["id"]
    assert (
        client.post_json(
            f"/api/admin/catalog/products/{pid}/prices",
            {"label": "Regular", "amount_cents": 5000, "starts_at": f"{YEAR}-01-01"},
        ).status_code
        == 201
    )
    assert (
        client.post_json(
            f"/api/admin/catalog/products/{pid}/grants",
            {
                "kind": "day_visits",
                "valid_from": f"{YEAR}-01-01",
                "valid_to": f"{YEAR}-12-31",
                "visit_count": 1,
            },
        ).status_code
        == 201
    )
    rule = client.post_json(
        f"/api/admin/catalog/products/{pid}/rules",
        {
            "kind": "requires_active_entitlement",
            "parameters": {"kind": "membership", "season_year": str(YEAR)},
            "failure_message": "Members only",
        },
    )
    assert rule.status_code == 201, rule.content
    product = rule.json()
    assert product["rules"][0]["parameters"] == {"kind": "membership", "season_year": YEAR}

    bad = client.post_json(
        f"/api/admin/catalog/products/{pid}/rules",
        {"kind": "age_at_least", "parameters": {"years": "old"}, "failure_message": "x"},
    )
    assert bad.status_code == 400
    unknown = client.post_json(
        f"/api/admin/catalog/products/{pid}/rules",
        {"kind": "profile_complete", "parameters": {"years": 3}, "failure_message": "x"},
    )
    assert unknown.status_code == 400

    rule_id = product["rules"][0]["id"]
    after = client.delete(f"/api/admin/catalog/products/{pid}/rules/{rule_id}").json()
    assert after["rules"] == []
    assert (
        client.get("/api/admin/catalog/options").json()["rule_kinds"][0]["kind"]
        == "requires_active_entitlement"
    )


def test_a_sold_price_cannot_be_deleted(client, pin_today):
    load_sample_catalog(YEAR)
    _admin(client, pin_today)
    buyer = _buyer("b@example.com", "B", "U")
    day_pass = Product.objects.get(name=f"Day Pass {YEAR}")
    orders.place_order(buyer, [day_pass.id], PaymentMethod.CASH, TODAY)
    price_id = day_pass.prices.first().id
    response = client.delete(f"/api/admin/catalog/products/{day_pass.id}/prices/{price_id}")
    assert response.status_code == 400 and "sold" in response.json()["detail"]


def test_rollover_copies_a_season_forward_inactive_and_only_once(client, pin_today):
    load_sample_catalog(YEAR)
    _admin(client, pin_today)
    created = client.post_json(
        "/api/admin/catalog/rollover", {"from_year": YEAR, "to_year": YEAR + 1}
    ).json()
    assert len(created) == 6
    names = {p["name"] for p in created}
    assert f"Adult Season Pass {YEAR + 1}" in names and all(not p["active"] for p in created)
    season = next(p for p in created if p["name"] == f"Adult Season Pass {YEAR + 1}")
    assert season["prices"][0]["starts_at"] == f"{YEAR + 1}-01-01"
    assert season["grants"][0]["valid_to"] == f"{YEAR + 1}-12-31"
    shuttle = next(p for p in created if p["name"].startswith("Member Day Shuttle"))
    gate = next(r for r in shuttle["rules"] if r["kind"] == "requires_active_entitlement")
    assert gate["parameters"]["season_year"] == YEAR + 1
    assert gate["failure_message"] == f"Needs an active {YEAR + 1} membership"
    again = client.post_json(
        "/api/admin/catalog/rollover", {"from_year": YEAR, "to_year": YEAR + 1}
    ).json()
    assert again == []
    assert (
        client.post_json(
            "/api/admin/catalog/rollover", {"from_year": YEAR, "to_year": YEAR}
        ).status_code
        == 400
    )


def test_reports_list_run_and_export(client, pin_today):
    load_sample_catalog(YEAR)
    _admin(client, pin_today)
    buyer = _buyer("r@example.com", "Rep", "Ort")
    membership = Product.objects.get(name=f"Adult SWS Membership {YEAR}")
    orders.place_order(buyer, [membership.id], PaymentMethod.CASH, TODAY)

    listed = client.get("/api/admin/reports").json()
    names = [r["name"] for r in listed]
    assert "sales_by_product" in names and "cards_to_print" in names
    sales = client.post_json(
        "/api/admin/reports/sales_by_product/run", {"parameters": {"season_year": YEAR}}
    ).json()
    assert sales["columns"] == ["Product", "Paid by", "Sold", "Revenue (CAD)"]
    assert [membership.name, "cash", 1, 40.0] in sales["rows"]
    active = client.post_json(
        "/api/admin/reports/active_memberships/run", {"parameters": {"on": TODAY.isoformat()}}
    ).json()
    assert ["Total", 1] in active["rows"]
    cards = client.post_json(
        "/api/admin/reports/cards_to_print/run", {"parameters": {"on": TODAY.isoformat()}}
    ).json()
    assert [buyer.id, buyer.member_number, "Rep Ort", "yes"] in cards["rows"]
    months = client.post_json(
        "/api/admin/reports/new_members_by_month/run",
        {"parameters": {"season_year": date.today().year}},
    ).json()
    assert months["rows"] and months["rows"][0][1] >= 2
    csv_out = client.post_json(
        "/api/admin/reports/sales_by_product/csv", {"parameters": {"season_year": YEAR}}
    )
    assert csv_out.headers["content-type"].startswith("text/csv")
    assert csv_out.content.decode().splitlines()[0] == "Product,Paid by,Sold,Revenue (CAD)"
    assert client.post_json("/api/admin/reports/nope/run", {}).status_code == 404
    assert (
        client.post_json(
            "/api/admin/reports/attendance_by_day/run", {"parameters": {"since": "not a date"}}
        ).status_code
        == 400
    )


def test_waiver_history_lists_versions_and_resets(client, pin_today):
    _admin(client, pin_today)
    client.post_json("/api/admin/waiver/publish", {"title": "v1", "body_text": "one"})
    client.post_json("/api/admin/waiver/reset", {"reason": "Insurer"})
    history = client.get("/api/admin/waiver/history").json()
    assert [t["version"] for t in history["templates"]] == [1]
    assert history["resets"][0]["reason"] == "Insurer"
