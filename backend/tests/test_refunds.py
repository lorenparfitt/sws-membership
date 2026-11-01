from datetime import date

import pytest

from sws_membership.catalog.models import Product
from sws_membership.catalog.sample_data import load_sample_catalog
from sws_membership.entitlements.models import Entitlement
from sws_membership.kiosk import service as kiosk
from sws_membership.kiosk.models import Station
from sws_membership.members.models import MemberRole
from sws_membership.orders import service
from sws_membership.orders.models import OrderStatus, PaymentMethod, Refund
from sws_membership.payments.processor import RefundResult
from tests.conftest import make_eligible, make_member

pytestmark = pytest.mark.django_db

YEAR = 2026
TODAY = date(YEAR, 6, 15)


def _member(email, roles=()):
    member = make_member(email, roles=roles, first_name="Re", last_name="Fund")
    make_eligible(member)
    return member


def _product(name) -> Product:
    return Product.objects.get(name=f"{name} {YEAR}")


@pytest.fixture
def catalog(pin_today):
    load_sample_catalog(YEAR)
    pin_today(TODAY)


@pytest.fixture
def admin(catalog):
    return _member("admin@example.com", roles=[MemberRole.ADMIN])


def _paid_by_card(client, member, *names):
    """Buy online and approve through the fake processor, as a member would."""
    client.sign_in(member)
    body = client.post_json("/api/orders", {"product_ids": [_product(n).id for n in names]}).json()
    assert client.post(f"/api/payments/fake/approve/{body['id']}").json() == {"status": "paid"}
    return body["id"]


def test_a_cash_refund_is_recorded_and_withdraws_the_passes(client, admin, mailer):
    member = _member("cash@example.com")
    order = service.place_order(
        member, [_product("Adult Season Pass").id], PaymentMethod.CASH, TODAY
    )
    assert all(e.order_line is not None for e in Entitlement.objects.filter(member=member))

    client.sign_in(admin)
    response = client.post_json(
        f"/api/admin/orders/{order.id}/refund", {"reason": "Moved away before the season"}
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["status"] == "refunded"
    assert body["refund"]["amount_cents"] == order.total_cents
    assert body["refund"]["reason"] == "Moved away before the season"
    assert body["refund"]["refunded_by"] == "Re Fund"

    refund = Refund.objects.get(order=order)
    assert refund.payment is None and refund.processor == "" and refund.transaction_id == ""
    assert refund.refunded_by == admin
    rows = Entitlement.objects.filter(member=member)
    assert rows.count() == 2 and all(e.revoked_at == refund.refunded_at for e in rows)
    assert not any(e.is_active_on(TODAY) for e in rows)

    # The member sees nothing held, and the gate admits nothing.
    client.sign_in(member)
    assert client.get("/api/entitlements").json() == []
    staff = _member("gate@example.com", roles=[MemberRole.STAFF])
    with pytest.raises(kiosk.CheckInRefused):
        kiosk.check_in(member, staff, Station.SPIT, TODAY)

    # The refunded membership no longer counts, so the same products can be bought again.
    again = service.quote(member, [_product("Adult Season Pass").id], TODAY)
    assert again.refused == {}

    notice = mailer.sent[-1]
    assert notice.to == member.email
    assert f"order {order.id}" in notice.subject
    assert "in cash at the counter" in notice.text
    assert "no longer valid" in notice.text


def test_a_card_refund_goes_through_the_processor_against_the_payment(
    client, admin, processor, mailer
):
    member = _member("card@example.com")
    order_id = _paid_by_card(client, member, "Adult SWS Membership", "Member Day Shuttle Pass")

    client.sign_in(admin)
    response = client.post_json(f"/api/admin/orders/{order_id}/refund", {"reason": "Duplicate"})
    assert response.status_code == 200, response.content
    assert response.json()["status"] == "refunded"

    refund = Refund.objects.get(order_id=order_id)
    payment = refund.payment
    assert payment is not None and payment.approved and payment.order_id == order_id
    assert len(processor.refunds) == 1
    asked = processor.refunds[0].raw
    assert asked["relatedTransactionId"] == payment.transaction_id
    assert asked["amount_cents"] == "6500" and asked["reference"] == str(order_id)
    assert refund.processor == "fake"
    assert refund.transaction_id == f"refund-of-{payment.transaction_id}"
    assert refund.amount_cents == 6500
    assert "to the card that paid" in mailer.sent[-1].text

    client.sign_in(member)
    assert client.get("/api/entitlements").json() == []
    listed = client.get("/api/orders").json()
    assert listed[0]["status"] == "refunded" and listed[0]["refund"]["reason"] == "Duplicate"


def test_a_declined_processor_refund_changes_nothing(client, admin, processor, monkeypatch):
    member = _member("declined@example.com")
    order_id = _paid_by_card(client, member, "Day Pass")

    def decline(transaction_id, amount_cents, currency, reference):
        return RefundResult(
            processor="fake",
            transaction_id="",
            approved=False,
            raw={},
            reason="Settled too long ago",
        )

    monkeypatch.setattr(processor, "refund", decline)
    client.sign_in(admin)
    response = client.post_json(f"/api/admin/orders/{order_id}/refund", {"reason": "Oops"})
    assert response.status_code == 409
    assert response.json()["detail"] == "Settled too long ago"
    assert Refund.objects.count() == 0
    assert client.get(f"/api/staff/orders/{order_id}").json()["status"] == "paid"
    assert Entitlement.objects.get(member=member).revoked_at is None


def test_only_a_paid_order_can_be_refunded_and_only_once(client, admin):
    member = _member("state@example.com")
    client.sign_in(member)
    pending = client.post_json("/api/orders", {"product_ids": [_product("Day Pass").id]}).json()
    paid = service.place_order(member, [_product("Day Pass").id], PaymentMethod.FREE, TODAY)

    client.sign_in(admin)
    assert (
        client.post_json(f"/api/admin/orders/{pending['id']}/refund", {"reason": "x"}).status_code
        == 409
    )
    assert (
        client.post_json(f"/api/admin/orders/{paid.id}/refund", {"reason": "x"}).status_code == 200
    )
    assert (
        client.post_json(f"/api/admin/orders/{paid.id}/refund", {"reason": "x"}).status_code == 409
    )
    assert client.post_json("/api/admin/orders/999999/refund", {"reason": "x"}).status_code == 404
    assert Refund.objects.filter(order=paid).count() == 1


def test_refunds_are_for_admins_only(client, catalog):
    member = _member("plain@example.com")
    staff = _member("staff@example.com", roles=[MemberRole.STAFF])
    order = service.place_order(member, [_product("Day Pass").id], PaymentMethod.CASH, TODAY)
    for who in (member, staff):
        client.sign_in(who)
        assert (
            client.post_json(f"/api/admin/orders/{order.id}/refund", {"reason": "x"}).status_code
            == 403
        )
    client.logout()
    assert (
        client.post_json(f"/api/admin/orders/{order.id}/refund", {"reason": "x"}).status_code == 401
    )
    order.refresh_from_db()
    assert order.status == OrderStatus.PAID


def test_the_staff_member_view_shows_the_refund(client, admin):
    member = _member("detail@example.com")
    order = service.place_order(member, [_product("Day Pass").id], PaymentMethod.CASH, TODAY)
    client.sign_in(admin)
    client.post_json(f"/api/admin/orders/{order.id}/refund", {"reason": "Rained out"})
    detail = client.get(f"/api/staff/members/{member.id}").json()
    assert detail["passes"] == []
    assert detail["orders"][0]["status"] == "refunded"
    assert detail["orders"][0]["refund"]["reason"] == "Rained out"
    assert detail["orders"][0]["refund"]["refunded_by"] == "Re Fund"
