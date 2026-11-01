from datetime import date

import pytest

from sws_membership.catalog.models import Product
from sws_membership.catalog.sample_data import load_sample_catalog
from sws_membership.entitlements.models import Entitlement
from sws_membership.members.models import MemberRole
from sws_membership.orders import service
from sws_membership.orders.models import Order, OrderStatus, PaymentMethod
from sws_membership.payments.processor import PaymentNotification
from tests.conftest import ApiClient, make_eligible, make_member

pytestmark = pytest.mark.django_db

YEAR = 2026
TODAY = date(YEAR, 6, 15)


def _member(email, birth=date(1990, 1, 1), roles=()):
    member = make_member(email, roles=roles, first_name="Ord", last_name="Er", date_of_birth=birth)
    make_eligible(member)
    return member


def _product(name) -> Product:
    return Product.objects.get(name=f"{name} {YEAR}")


def _entitlements(member):
    return list(Entitlement.objects.filter(member=member))


@pytest.fixture
def catalog(pin_today):
    load_sample_catalog(YEAR)
    pin_today(TODAY)


def test_cash_order_is_paid_at_once_and_issues_every_grant(catalog):
    member = _member("cash@example.com")
    season = _product("Adult Season Pass")
    order = service.place_order(member, [season.id], PaymentMethod.CASH, TODAY)
    assert order.status == OrderStatus.PAID
    assert order.total_cents == 30000  # regular price in June
    assert [line.product_name for line in order.lines.all()] == [season.name]
    assert sorted(e.kind for e in _entitlements(member)) == ["membership", "season_access"]


def test_card_order_waits_for_the_processor(catalog):
    member = _member("card@example.com")
    membership = _product("Adult SWS Membership")
    order = service.place_order(member, [membership.id], PaymentMethod.CARD, TODAY)
    assert order.status == OrderStatus.PENDING_PAYMENT
    assert _entitlements(member) == []


def test_an_ineligible_product_refuses_the_whole_order(catalog):
    member = _member("youth@example.com", birth=date(YEAR - 15, 1, 1))
    adult = _product("Adult SWS Membership")
    day_pass = _product("Day Pass")
    with pytest.raises(service.OrderRefused) as refused:
        service.place_order(member, [day_pass.id, adult.id], PaymentMethod.CASH, TODAY)
    assert refused.value.reasons == {adult.name: ["For members 19 and over"]}
    assert Order.objects.count() == 0


def test_a_membership_in_the_same_basket_opens_the_gate_and_the_member_price(catalog):
    """Membership and shuttle in one basket: the membership counts, whichever order."""
    member = _member("basket@example.com")
    membership = _product("Adult SWS Membership")
    shuttle = _product("Member Day Shuttle Pass")
    with pytest.raises(service.OrderRefused) as refused:
        service.place_order(member, [shuttle.id], PaymentMethod.CASH, TODAY)
    assert f"Needs an active {YEAR} membership" in refused.value.reasons[shuttle.name]

    quoted = service.quote(member, [shuttle.id, membership.id], TODAY)
    assert quoted.refused == {}
    assert [(l.product_name, l.amount_cents) for l in quoted.lines] == [
        (shuttle.name, 2500),
        (membership.name, 4000),
    ]

    order = service.place_order(member, [shuttle.id, membership.id], PaymentMethod.CASH, TODAY)
    assert order.total_cents == 6500
    assert sorted(e.kind for e in _entitlements(member)) == ["membership", "shuttle_access"]

    # Bought once, the membership is now held for real and refuses a repeat.
    again = service.quote(member, [membership.id], TODAY)
    assert again.refused == {membership.name: ["Already held for this season"]}


def test_a_basket_lists_every_product_once(catalog):
    member = _member("twice@example.com")
    day_pass = _product("Day Pass")
    with pytest.raises(service.OrderRefused) as refused:
        service.quote(member, [day_pass.id, day_pass.id], TODAY)
    assert refused.value.reasons == {"order": [f"product {day_pass.id} listed twice"]}


def _notification(order, approved=True, transaction_id="tx-1", amount=None) -> PaymentNotification:
    return PaymentNotification(
        order_id=order.id,
        transaction_id=transaction_id,
        approved=approved,
        amount_cents=order.total_cents if amount is None else amount,
        currency="CAD",
        raw={"Status": "APPROVED" if approved else "DECLINED"},
    )


def test_an_approved_notification_pays_the_order_once(catalog):
    member = _member("pay@example.com")
    order = service.place_order(member, [_product("Day Pass").id], PaymentMethod.CARD, TODAY)
    first, paid_now = service.record_payment("fake", _notification(order))
    again, paid_again = service.record_payment("fake", _notification(order))
    assert first == again and paid_now is True and paid_again is False
    order.refresh_from_db()
    assert order.status == OrderStatus.PAID and order.paid_at is not None
    assert len(_entitlements(member)) == 1


def test_a_declined_or_short_notification_leaves_the_order_pending(catalog):
    member = _member("short@example.com")
    order = service.place_order(member, [_product("Day Pass").id], PaymentMethod.CARD, TODAY)
    service.record_payment("fake", _notification(order, approved=False, transaction_id="d"))
    service.record_payment("fake", _notification(order, amount=1, transaction_id="s"))
    order.refresh_from_db()
    assert order.status == OrderStatus.PENDING_PAYMENT
    assert order.payments.count() == 2
    assert _entitlements(member) == []


# --- through the API -------------------------------------------------------


def _webhook_form(processor, order_id, total_cents, transaction_id="fake-tx-9", status="APPROVED"):
    return {
        "order_id": str(order_id),
        "transaction_id": transaction_id,
        "status": status,
        "amount_cents": str(total_cents),
        "checksum": processor.checksum(str(order_id), transaction_id, status),
    }


def test_member_checkout_returns_a_processor_session_and_the_webhook_pays_it(
    client, catalog, processor
):
    member = _member("web@example.com")
    client.sign_in(member)
    created = client.post_json("/api/orders", {"product_ids": [_product("Day Pass").id]})
    assert created.status_code == 201, created.content
    body = created.json()
    assert body["status"] == "pending_payment"
    assert body["checkout"]["processor"] == "fake"
    assert body["checkout"]["session_token"] == f"fake-session-{body['id']}"

    # The processor posts from its own servers: no session, no CSRF token.
    webhook = ApiClient(enforce_csrf_checks=True)
    posted = webhook.post(
        "/api/payments/notification", _webhook_form(processor, body["id"], body["total_cents"])
    )
    assert posted.status_code == 200 and posted.content == b"OK"
    assert client.get(f"/api/orders/{body['id']}").json()["status"] == "paid"


def test_a_forged_webhook_is_rejected_and_pays_nothing(client, catalog):
    member = _member("forge@example.com")
    client.sign_in(member)
    order_id = client.post_json("/api/orders", {"product_ids": [_product("Day Pass").id]}).json()[
        "id"
    ]
    forged = {
        "order_id": str(order_id),
        "transaction_id": "x",
        "status": "APPROVED",
        "checksum": "nope",
    }
    assert client.post("/api/payments/notification", forged).status_code == 400
    assert client.get(f"/api/orders/{order_id}").json()["status"] == "pending_payment"


def test_refused_checkout_explains_itself(client, catalog):
    client.sign_in(_member("locked@example.com"))
    shuttle = _product("Member Day Shuttle Pass")
    response = client.post_json("/api/orders", {"product_ids": [shuttle.id]})
    assert response.status_code == 409
    assert response.json()["detail"]["refused"] == {
        shuttle.name: [f"Needs an active {YEAR} membership"]
    }


def test_staff_ring_up_cash_or_open_a_card_form_for_another_member(client, catalog):
    staff = _member("staff@example.com", roles=[MemberRole.STAFF])
    buyer = _member("buyer@example.com")
    client.sign_in(staff)
    day_pass = _product("Day Pass")
    paid = client.post_json(
        "/api/staff/orders",
        {"member_id": buyer.id, "product_ids": [day_pass.id], "payment_method": "cash"},
    )
    assert paid.status_code == 201, paid.content
    assert paid.json()["status"] == "paid"
    assert Order.objects.get(id=paid.json()["id"]).created_by_id == staff.id
    assert len(_entitlements(buyer)) == 1

    card = client.post_json(
        "/api/staff/orders",
        {"member_id": buyer.id, "product_ids": [day_pass.id], "payment_method": "card"},
    )
    assert card.status_code == 201, card.content
    body = card.json()
    assert body["status"] == "pending_payment" and body["checkout"]["processor"] == "fake"
    assert client.get(f"/api/staff/orders/{body['id']}").json()["status"] == "pending_payment"
    assert client.post(f"/api/payments/fake/approve/{body['id']}").json() == {"status": "paid"}
    assert client.get(f"/api/staff/orders/{body['id']}").json()["status"] == "paid"


def test_plain_members_cannot_use_the_staff_till(client, catalog):
    member = _member("plain@example.com")
    client.sign_in(member)
    response = client.post_json(
        "/api/staff/orders",
        {
            "member_id": member.id,
            "product_ids": [_product("Day Pass").id],
            "payment_method": "free",
        },
    )
    assert response.status_code == 403


def test_members_see_only_their_own_orders(client, catalog):
    alice = _member("alice@example.com")
    bob = _member("bob@example.com")
    order = service.place_order(alice, [_product("Day Pass").id], PaymentMethod.CASH, TODAY)
    client.sign_in(bob)
    assert client.get(f"/api/orders/{order.id}").status_code == 404


def test_fake_approve_pays_the_members_own_order_through_the_real_path(client, catalog):
    member = _member("approve@example.com")
    client.sign_in(member)
    order_id = client.post_json("/api/orders", {"product_ids": [_product("Day Pass").id]}).json()[
        "id"
    ]
    assert client.post(f"/api/payments/fake/approve/{order_id}").json() == {"status": "paid"}
    assert client.get(f"/api/orders/{order_id}").json()["status"] == "paid"
    passes = client.get("/api/entitlements").json()
    assert [(p["kind"], p["visits_remaining"], p["active"]) for p in passes] == [
        ("day_visits", 1, True)
    ]

    client.sign_in(_member("other@example.com"))
    assert client.post(f"/api/payments/fake/approve/{order_id}").status_code == 404


def test_members_list_their_own_orders_newest_first_with_receipts_once_paid(client, catalog):
    member = _member("history@example.com")
    client.sign_in(member)
    day_pass = _product("Day Pass")
    first = client.post_json("/api/orders", {"product_ids": [day_pass.id]}).json()["id"]
    second = client.post_json("/api/orders", {"product_ids": [day_pass.id]}).json()["id"]
    assert client.post(f"/api/payments/fake/approve/{second}").json() == {"status": "paid"}

    listed = client.get("/api/orders").json()
    assert [(o["id"], o["status"]) for o in listed] == [
        (second, "paid"),
        (first, "pending_payment"),
    ]
    assert listed[0]["paid_at"] is not None and listed[1]["paid_at"] is None

    receipt = client.get(f"/api/orders/{second}/receipt")
    assert receipt.status_code == 200
    assert f"order {second} is paid" in receipt.content.decode()
    assert client.get(f"/api/orders/{first}/receipt").status_code == 409


def test_a_closed_card_form_can_be_reopened_until_the_order_is_paid(client, catalog):
    member = _member("reopen@example.com")
    client.sign_in(member)
    order_id = client.post_json("/api/orders", {"product_ids": [_product("Day Pass").id]}).json()[
        "id"
    ]

    reopened = client.post(f"/api/orders/{order_id}/checkout")
    assert reopened.status_code == 200, reopened.content
    assert reopened.json()["checkout"]["session_token"] == f"fake-session-{order_id}"

    client.post(f"/api/payments/fake/approve/{order_id}")
    assert client.post(f"/api/orders/{order_id}/checkout").status_code == 409

    cash = service.place_order(member, [_product("Day Pass").id], PaymentMethod.CASH, TODAY)
    assert client.post(f"/api/orders/{cash.id}/checkout").status_code == 409


def test_cancelling_withdraws_an_unpaid_card_order_but_money_still_wins(client, catalog):
    member = _member("cancel@example.com")
    client.sign_in(member)
    day_pass = _product("Day Pass")
    order_id = client.post_json("/api/orders", {"product_ids": [day_pass.id]}).json()["id"]

    cancelled = client.post(f"/api/orders/{order_id}/cancel")
    assert cancelled.status_code == 200, cancelled.content
    assert cancelled.json()["status"] == "cancelled"
    assert client.post(f"/api/orders/{order_id}/cancel").status_code == 409
    assert client.post(f"/api/orders/{order_id}/checkout").status_code == 409

    # The processor's notification for a charge that already went through
    # arrives after the cancel: the member paid, so the member gets the pass.
    assert client.post(f"/api/payments/fake/approve/{order_id}").json() == {"status": "paid"}
    assert client.get("/api/entitlements").json()[0]["kind"] == "day_visits"

    paid = service.place_order(member, [day_pass.id], PaymentMethod.CASH, TODAY)
    assert client.post(f"/api/orders/{paid.id}/cancel").status_code == 409


def test_order_history_actions_are_scoped_to_the_owner_or_staff(client, catalog):
    alice = _member("alice2@example.com")
    bob = _member("bob2@example.com")
    clerk = _member("clerk2@example.com", roles=[MemberRole.STAFF])
    client.sign_in(alice)
    order_id = client.post_json("/api/orders", {"product_ids": [_product("Day Pass").id]}).json()[
        "id"
    ]

    client.sign_in(bob)
    assert client.get("/api/orders").json() == []
    assert client.post(f"/api/orders/{order_id}/checkout").status_code == 404
    assert client.post(f"/api/orders/{order_id}/cancel").status_code == 404
    assert client.post(f"/api/staff/orders/{order_id}/cancel").status_code == 403

    client.sign_in(clerk)
    assert client.post(f"/api/staff/orders/{order_id}/checkout").status_code == 200
    assert client.post(f"/api/staff/orders/{order_id}/cancel").json()["status"] == "cancelled"
    assert client.get(f"/api/staff/orders/{order_id}/receipt").status_code == 409


def test_the_quote_route_prices_a_basket_without_creating_an_order(client, catalog):
    member = _member("quote@example.com")
    client.sign_in(member)
    membership = _product("Adult SWS Membership")
    shuttle = _product("Member Day Shuttle Pass")
    youth = _product("Youth SWS Membership")

    alone = client.post_json("/api/orders/quote", {"product_ids": [shuttle.id]}).json()
    assert alone["lines"] == [] and alone["total_cents"] == 0
    assert f"Needs an active {YEAR} membership" in alone["refused"][shuttle.name]

    both = client.post_json(
        "/api/orders/quote", {"product_ids": [membership.id, shuttle.id, youth.id]}
    ).json()
    assert [l["product_id"] for l in both["lines"]] == [membership.id, shuttle.id]
    assert both["total_cents"] == 6500 and both["currency"] == "CAD"
    assert both["refused"] == {youth.name: ["For members 18 and under"]}
    assert client.get("/api/orders").json() == []

    client.sign_in(_member("clerk3@example.com", roles=[MemberRole.STAFF]))
    staff = client.post_json(
        "/api/staff/orders/quote",
        {"member_id": member.id, "product_ids": [membership.id, shuttle.id]},
    ).json()
    assert staff["total_cents"] == 6500
