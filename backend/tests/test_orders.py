from datetime import date

import pytest
from sqlalchemy import select

from sws_membership.auth import service as auth
from sws_membership.auth.dependencies import SESSION_COOKIE
from sws_membership.catalog.models import Product
from sws_membership.catalog.router import current_day
from sws_membership.catalog.sample_data import load_sample_catalog
from sws_membership.entitlements.models import Entitlement, EntitlementKind
from sws_membership.members.member_numbers import allocate_member_number
from sws_membership.members.models import Member, MemberRole, MemberRoleAssignment
from sws_membership.orders import service
from sws_membership.orders.models import Order, OrderStatus, PaymentMethod
from sws_membership.payments.fake import FakeProcessor
from sws_membership.payments.processor import PaymentNotification
from tests.conftest import sign_current_waiver

YEAR = 2026
TODAY = date(YEAR, 6, 15)


def _member(session, email, birth=date(1990, 1, 1), roles=()) -> Member:
    member = Member(
        member_number=allocate_member_number(session),
        first_name="Ord",
        last_name="Er",
        email=email,
        date_of_birth=birth,
        roles=[MemberRoleAssignment(role=r) for r in roles],
    )
    session.add(member)
    session.flush()
    sign_current_waiver(session, member)
    return member


def _product(session, name) -> Product:
    return session.scalars(select(Product).where(Product.name == f"{name} {YEAR}")).one()


def _entitlements(session, member):
    return session.scalars(select(Entitlement).where(Entitlement.member_id == member.id)).all()


@pytest.fixture
def catalog(session):
    load_sample_catalog(session, YEAR)


def test_cash_order_is_paid_at_once_and_issues_every_grant(session, catalog):
    member = _member(session, "cash@example.com")
    season = _product(session, "Adult Season Pass")
    order = service.place_order(session, member, [season.id], PaymentMethod.CASH, TODAY)
    assert order.status is OrderStatus.PAID
    assert order.total_cents == 30000  # regular price in June
    assert [line.product_name for line in order.lines] == [season.name]
    kinds = sorted((e.kind for e in _entitlements(session, member)), key=lambda k: k.value)
    assert kinds == [EntitlementKind.MEMBERSHIP, EntitlementKind.SEASON_ACCESS]


def test_card_order_waits_for_the_processor(session, catalog):
    member = _member(session, "card@example.com")
    membership = _product(session, "Adult SWS Membership")
    order = service.place_order(session, member, [membership.id], PaymentMethod.CARD, TODAY)
    assert order.status is OrderStatus.PENDING_PAYMENT
    assert _entitlements(session, member) == []


def test_an_ineligible_product_refuses_the_whole_order(session, catalog):
    member = _member(session, "youth@example.com", birth=date(YEAR - 15, 1, 1))
    adult = _product(session, "Adult SWS Membership")
    day_pass = _product(session, "Day Pass")
    with pytest.raises(service.OrderRefused) as refused:
        service.place_order(session, member, [day_pass.id, adult.id], PaymentMethod.CASH, TODAY)
    assert refused.value.reasons == {adult.name: ["For members 19 and over"]}
    assert session.scalars(select(Order)).all() == []


def test_the_gate_opens_within_one_order_only_after_payment(session, catalog):
    """Membership and shuttle in one basket: the shuttle is still gated."""
    member = _member(session, "basket@example.com")
    membership = _product(session, "Adult SWS Membership")
    shuttle = _product(session, "Member Day Shuttle Pass")
    with pytest.raises(service.OrderRefused):
        service.place_order(session, member, [membership.id, shuttle.id], PaymentMethod.CASH, TODAY)
    service.place_order(session, member, [membership.id], PaymentMethod.CASH, TODAY)
    order = service.place_order(session, member, [shuttle.id], PaymentMethod.CASH, TODAY)
    assert order.total_cents == 2500


def _notification(order, approved=True, transaction_id="tx-1", amount=None) -> PaymentNotification:
    return PaymentNotification(
        order_id=order.id,
        transaction_id=transaction_id,
        approved=approved,
        amount_cents=order.total_cents if amount is None else amount,
        currency="CAD",
        raw={"Status": "APPROVED" if approved else "DECLINED"},
    )


def test_an_approved_notification_pays_the_order_once(session, catalog):
    member = _member(session, "pay@example.com")
    order = service.place_order(
        session, member, [_product(session, "Day Pass").id], PaymentMethod.CARD, TODAY
    )
    first = service.record_payment(session, "fake", _notification(order))
    again = service.record_payment(session, "fake", _notification(order))
    assert first is again
    assert order.status is OrderStatus.PAID
    assert len(_entitlements(session, member)) == 1


def test_a_declined_or_short_notification_leaves_the_order_pending(session, catalog):
    member = _member(session, "declined@example.com")
    order = service.place_order(
        session, member, [_product(session, "Day Pass").id], PaymentMethod.CARD, TODAY
    )
    service.record_payment(
        session, "fake", _notification(order, approved=False, transaction_id="a")
    )
    service.record_payment(session, "fake", _notification(order, amount=1, transaction_id="b"))
    assert order.status is OrderStatus.PENDING_PAYMENT
    assert len(order.payments) == 2
    assert _entitlements(session, member) == []


# --- through the API -------------------------------------------------------


def _sign_in(session, client, member):
    client.cookies.set(SESSION_COOKIE, auth.open_session(session, member))
    client.app.dependency_overrides[current_day] = lambda: TODAY


def test_member_checkout_returns_a_processor_session_and_the_webhook_pays_it(
    session, client, catalog
):
    member = _member(session, "web@example.com")
    _sign_in(session, client, member)
    day_pass = _product(session, "Day Pass")
    created = client.post("/api/orders", json={"product_ids": [day_pass.id]})
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "pending_payment"
    assert body["checkout"]["processor"] == "fake"
    assert body["checkout"]["session_token"] == f"fake-session-{body['id']}"

    processor: FakeProcessor = client.app.state.payment_processor
    form = {
        "order_id": str(body["id"]),
        "transaction_id": "fake-tx-9",
        "status": "APPROVED",
        "amount_cents": str(body["total_cents"]),
        "checksum": processor.checksum(str(body["id"]), "fake-tx-9", "APPROVED"),
    }
    assert client.post("/api/payments/notification", data=form).text == '"OK"'
    assert client.get(f"/api/orders/{body['id']}").json()["status"] == "paid"


def test_a_forged_webhook_is_rejected_and_pays_nothing(session, client, catalog):
    member = _member(session, "forge@example.com")
    _sign_in(session, client, member)
    order_id = client.post(
        "/api/orders", json={"product_ids": [_product(session, "Day Pass").id]}
    ).json()["id"]
    forged = {
        "order_id": str(order_id),
        "transaction_id": "x",
        "status": "APPROVED",
        "checksum": "nope",
    }
    assert client.post("/api/payments/notification", data=forged).status_code == 400
    assert client.get(f"/api/orders/{order_id}").json()["status"] == "pending_payment"


def test_refused_checkout_explains_itself(session, client, catalog):
    member = _member(session, "locked@example.com")
    _sign_in(session, client, member)
    shuttle = _product(session, "Member Day Shuttle Pass")
    response = client.post("/api/orders", json={"product_ids": [shuttle.id]})
    assert response.status_code == 409
    assert response.json()["detail"]["refused"] == {
        shuttle.name: [f"Needs an active {YEAR} membership"]
    }


def test_staff_ring_up_cash_for_another_member_but_not_card(session, client, catalog):
    staff = _member(session, "staff@example.com", roles=[MemberRole.STAFF])
    buyer = _member(session, "buyer@example.com")
    _sign_in(session, client, staff)
    day_pass = _product(session, "Day Pass")
    paid = client.post(
        "/api/staff/orders",
        json={"member_id": buyer.id, "product_ids": [day_pass.id], "payment_method": "cash"},
    )
    assert paid.status_code == 201, paid.text
    assert paid.json()["status"] == "paid"
    order = session.get(Order, paid.json()["id"])
    assert order.created_by_member_id == staff.id
    assert len(_entitlements(session, buyer)) == 1

    card = client.post(
        "/api/staff/orders",
        json={"member_id": buyer.id, "product_ids": [day_pass.id], "payment_method": "card"},
    )
    assert card.status_code == 400


def test_plain_members_cannot_use_the_staff_till(session, client, catalog):
    member = _member(session, "plain@example.com")
    _sign_in(session, client, member)
    response = client.post(
        "/api/staff/orders",
        json={"member_id": member.id, "product_ids": [1], "payment_method": "free"},
    )
    assert response.status_code == 403


def test_members_see_only_their_own_orders(session, client, catalog):
    alice = _member(session, "alice@example.com")
    bob = _member(session, "bob@example.com")
    order = service.place_order(
        session, alice, [_product(session, "Day Pass").id], PaymentMethod.CASH, TODAY
    )
    _sign_in(session, client, bob)
    assert client.get(f"/api/orders/{order.id}").status_code == 404


def test_fake_approve_pays_the_members_own_order_through_the_real_path(session, client, catalog):
    member = _member(session, "approve@example.com")
    _sign_in(session, client, member)
    order_id = client.post(
        "/api/orders", json={"product_ids": [_product(session, "Day Pass").id]}
    ).json()["id"]
    assert client.post(f"/api/payments/fake/approve/{order_id}").json() == {"status": "paid"}
    assert client.get(f"/api/orders/{order_id}").json()["status"] == "paid"
    passes = client.get("/api/entitlements").json()
    assert [(p["kind"], p["visits_remaining"], p["active"]) for p in passes] == [
        ("day_visits", 1, True)
    ]

    other = _member(session, "other@example.com")
    _sign_in(session, client, other)
    assert client.post(f"/api/payments/fake/approve/{order_id}").status_code == 404
