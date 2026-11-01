import json
from datetime import date

import httpx
import pytest

from sws_membership.catalog.models import Product
from sws_membership.catalog.sample_data import load_sample_catalog
from sws_membership.mail.mailchimp import MailchimpError, MailchimpTransactionalMailer
from sws_membership.mail.mailer import EmailMessage
from sws_membership.members.models import MemberRole
from tests.conftest import make_eligible, make_member

pytestmark = pytest.mark.django_db

YEAR = 2026
TODAY = date(YEAR, 6, 15)


def _member(email, roles=()):
    member = make_member(
        email, roles=roles, first_name="Rec", last_name="Eipt", date_of_birth=date(1990, 1, 1)
    )
    make_eligible(member)
    return member


def _day_pass(pin_today) -> Product:
    load_sample_catalog(YEAR)
    pin_today(TODAY)
    return Product.objects.get(name=f"Day Pass {YEAR}")


def _form(processor, order, transaction_id, status):
    return {
        "order_id": str(order["id"]),
        "transaction_id": transaction_id,
        "status": status,
        "amount_cents": str(order["total_cents"]),
        "checksum": processor.checksum(str(order["id"]), transaction_id, status),
    }


def test_webhook_payment_sends_one_receipt_even_when_redelivered(
    client, mailer, processor, pin_today
):
    member = _member("rec@example.com")
    client.sign_in(member)
    order = client.post_json("/api/orders", {"product_ids": [_day_pass(pin_today).id]}).json()
    form = _form(processor, order, "tx-receipt", "APPROVED")
    client.post("/api/payments/notification", form)
    client.post("/api/payments/notification", form)
    receipts = [m for m in mailer.sent if "receipt" in m.subject]
    assert len(receipts) == 1
    assert receipts[0].to == "rec@example.com"
    assert f"Day Pass {YEAR}" in receipts[0].text and "$    35.00" in receipts[0].text
    assert f"order {order['id']}" in receipts[0].subject


def test_declined_payment_sends_no_receipt(client, mailer, processor, pin_today):
    member = _member("nope@example.com")
    client.sign_in(member)
    order = client.post_json("/api/orders", {"product_ids": [_day_pass(pin_today).id]}).json()
    client.post("/api/payments/notification", _form(processor, order, "tx-declined", "DECLINED"))
    assert [m for m in mailer.sent if "receipt" in m.subject] == []


def test_counter_cash_sale_sends_a_receipt(client, mailer, pin_today):
    staff = _member("staff@example.com", roles=[MemberRole.STAFF])
    buyer = _member("buyer@example.com")
    client.sign_in(staff)
    response = client.post_json(
        "/api/staff/orders",
        {"member_id": buyer.id, "product_ids": [_day_pass(pin_today).id], "payment_method": "cash"},
    )
    assert response.status_code == 201
    receipts = [m for m in mailer.sent if "receipt" in m.subject]
    assert (
        len(receipts) == 1
        and receipts[0].to == "buyer@example.com"
        and "Paid by cash" in receipts[0].text
    )


def test_mailchimp_mailer_posts_the_message_and_raises_when_not_sent():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = request.read().decode()
        if "refuse-key" in body:
            return httpx.Response(401, json={"status": "error", "message": "Invalid API key"})
        if "bounce@" in body:
            return httpx.Response(
                200,
                json=[
                    {
                        "email": "bounce@example.com",
                        "status": "rejected",
                        "reject_reason": "hard-bounce",
                    }
                ],
            )
        return httpx.Response(200, json=[{"email": "a@example.com", "status": "sent"}])

    http = httpx.Client(
        base_url="https://mandrillapp.com/api/1.0", transport=httpx.MockTransport(handler)
    )
    mailer = MailchimpTransactionalMailer("good-key", "m@example.com", "SWS", client=http)
    mailer.send(EmailMessage(to="a@example.com", subject="Hi", text="hello"))
    assert seen[0].url.path == "/api/1.0/messages/send"
    sent = json.loads(seen[0].read())
    assert sent["key"] == "good-key"
    assert sent["message"]["from_email"] == "m@example.com"
    assert sent["message"]["to"] == [{"email": "a@example.com", "type": "to"}]
    with pytest.raises(MailchimpError):
        mailer.send(EmailMessage(to="bounce@example.com", subject="Hi", text="hello"))
    with pytest.raises(MailchimpError):
        MailchimpTransactionalMailer("refuse-key", "m@example.com", "SWS", client=http).send(
            EmailMessage(to="a@example.com", subject="Hi", text="hello")
        )
