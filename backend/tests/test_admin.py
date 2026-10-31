from datetime import date

from sqlalchemy import select

from sws_membership.auth import service as auth
from sws_membership.auth.dependencies import SESSION_COOKIE
from sws_membership.catalog.models import Product
from sws_membership.catalog.router import current_day
from sws_membership.catalog.sample_data import load_sample_catalog
from sws_membership.members.member_numbers import allocate_member_number
from sws_membership.members.models import Member, MemberRole, MemberRoleAssignment
from sws_membership.orders import service as orders
from sws_membership.orders.models import PaymentMethod
from tests.conftest import make_eligible

YEAR = 2026
TODAY = date(YEAR, 6, 15)


def _admin(session, client) -> Member:
    admin = Member(
        member_number=allocate_member_number(session),
        first_name="Ad",
        last_name="Min",
        email="admin@example.com",
        roles=[MemberRoleAssignment(role=MemberRole.ADMIN)],
    )
    session.add(admin)
    session.flush()
    client.cookies.set(SESSION_COOKIE, auth.open_session(session, admin))
    client.app.dependency_overrides[current_day] = lambda: TODAY
    return admin


def test_admin_routes_are_admin_only(session, client):
    staff = Member(
        member_number=allocate_member_number(session),
        first_name="S",
        last_name="T",
        email="staff@example.com",
        roles=[MemberRoleAssignment(role=MemberRole.STAFF)],
    )
    session.add(staff)
    session.flush()
    client.cookies.set(SESSION_COOKIE, auth.open_session(session, staff))
    assert client.get("/api/admin/catalog/products").status_code == 403
    assert client.get("/api/admin/reports").status_code == 403


def test_build_a_gated_product_from_nothing(session, client):
    _admin(session, client)
    created = client.post(
        "/api/admin/catalog/products",
        json={
            "name": "Foil Clinic 2026",
            "description": "One evening.",
            "season_year": YEAR,
            "sort_order": 70,
        },
    )
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    assert (
        client.post(
            f"/api/admin/catalog/products/{pid}/prices",
            json={"label": "Regular", "amount_cents": 5000, "starts_at": f"{YEAR}-01-01"},
        ).status_code
        == 201
    )
    assert (
        client.post(
            f"/api/admin/catalog/products/{pid}/grants",
            json={
                "kind": "day_visits",
                "valid_from": f"{YEAR}-01-01",
                "valid_to": f"{YEAR}-12-31",
                "visit_count": 1,
            },
        ).status_code
        == 201
    )
    rule = client.post(
        f"/api/admin/catalog/products/{pid}/rules",
        json={
            "kind": "requires_active_entitlement",
            "parameters": {"kind": "membership", "season_year": str(YEAR)},
            "failure_message": "Members only",
        },
    )
    assert rule.status_code == 201, rule.text
    product = rule.json()
    assert product["rules"][0]["parameters"] == {"kind": "membership", "season_year": YEAR}

    bad = client.post(
        f"/api/admin/catalog/products/{pid}/rules",
        json={"kind": "age_at_least", "parameters": {"years": "old"}, "failure_message": "x"},
    )
    assert bad.status_code == 400
    unknown = client.post(
        f"/api/admin/catalog/products/{pid}/rules",
        json={"kind": "profile_complete", "parameters": {"years": 3}, "failure_message": "x"},
    )
    assert unknown.status_code == 400

    rule_id = product["rules"][0]["id"]
    after = client.delete(f"/api/admin/catalog/products/{pid}/rules/{rule_id}").json()
    assert after["rules"] == []
    assert (
        client.get("/api/admin/catalog/options").json()["rule_kinds"][0]["kind"]
        == "requires_active_entitlement"
    )


def test_a_sold_price_cannot_be_deleted(session, client):
    load_sample_catalog(session, YEAR)
    _admin(session, client)
    buyer = Member(
        member_number=allocate_member_number(session),
        first_name="B",
        last_name="U",
        email="b@example.com",
        date_of_birth=date(1990, 1, 1),
    )
    session.add(buyer)
    session.flush()
    make_eligible(session, buyer)
    day_pass = session.scalars(select(Product).where(Product.name == f"Day Pass {YEAR}")).one()
    orders.place_order(session, buyer, [day_pass.id], PaymentMethod.CASH, TODAY)
    price_id = day_pass.prices[0].id
    response = client.delete(f"/api/admin/catalog/products/{day_pass.id}/prices/{price_id}")
    assert response.status_code == 400 and "sold" in response.json()["detail"]


def test_rollover_copies_a_season_forward_inactive_and_only_once(session, client):
    load_sample_catalog(session, YEAR)
    _admin(session, client)
    created = client.post(
        "/api/admin/catalog/rollover", json={"from_year": YEAR, "to_year": YEAR + 1}
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
    again = client.post(
        "/api/admin/catalog/rollover", json={"from_year": YEAR, "to_year": YEAR + 1}
    ).json()
    assert again == []
    assert (
        client.post(
            "/api/admin/catalog/rollover", json={"from_year": YEAR, "to_year": YEAR}
        ).status_code
        == 400
    )


def test_reports_list_run_and_export(session, client):
    load_sample_catalog(session, YEAR)
    _admin(session, client)
    buyer = Member(
        member_number=allocate_member_number(session),
        first_name="Rep",
        last_name="Ort",
        email="r@example.com",
        date_of_birth=date(1990, 1, 1),
    )
    session.add(buyer)
    session.flush()
    make_eligible(session, buyer)
    membership = session.scalars(
        select(Product).where(Product.name == f"Adult SWS Membership {YEAR}")
    ).one()
    orders.place_order(session, buyer, [membership.id], PaymentMethod.CASH, TODAY)

    listed = client.get("/api/admin/reports").json()
    names = [r["name"] for r in listed]
    assert "sales_by_product" in names and "cards_to_print" in names
    sales = client.post(
        "/api/admin/reports/sales_by_product/run", json={"parameters": {"season_year": YEAR}}
    ).json()
    assert sales["columns"] == ["Product", "Paid by", "Sold", "Revenue (CAD)"]
    assert [membership.name, "cash", 1, 40.0] in sales["rows"]
    active = client.post(
        "/api/admin/reports/active_memberships/run", json={"parameters": {"on": TODAY.isoformat()}}
    ).json()
    assert ["Total", 1] in active["rows"]
    cards = client.post(
        "/api/admin/reports/cards_to_print/run", json={"parameters": {"on": TODAY.isoformat()}}
    ).json()
    assert [buyer.id, buyer.member_number, "Rep Ort", "yes"] in cards["rows"]
    csv_out = client.post(
        "/api/admin/reports/sales_by_product/csv", json={"parameters": {"season_year": YEAR}}
    )
    assert csv_out.headers["content-type"].startswith("text/csv")
    assert csv_out.text.splitlines()[0] == "Product,Paid by,Sold,Revenue (CAD)"
    assert client.post("/api/admin/reports/nope/run", json={}).status_code == 404
    assert (
        client.post(
            "/api/admin/reports/attendance_by_day/run", json={"parameters": {"since": "not a date"}}
        ).status_code
        == 400
    )


def test_waiver_history_lists_versions_and_resets(session, client):
    _admin(session, client)
    client.post("/api/admin/waiver/publish", json={"title": "v1", "body_text": "one"})
    client.post("/api/admin/waiver/reset", json={"reason": "Insurer"})
    history = client.get("/api/admin/waiver/history").json()
    assert [t["version"] for t in history["templates"]] == [1]
    assert history["resets"][0]["reason"] == "Insurer"
