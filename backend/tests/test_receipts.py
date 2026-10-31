import json
from datetime import date

import httpx
import pytest
from sqlalchemy import select

from sws_membership.auth import service as auth
from sws_membership.auth.dependencies import SESSION_COOKIE
from sws_membership.catalog.models import Product
from sws_membership.catalog.router import current_day
from sws_membership.catalog.sample_data import load_sample_catalog
from sws_membership.mail.mailchimp import MailchimpError, MailchimpTransactionalMailer
from sws_membership.mail.mailer import EmailMessage
from sws_membership.members.member_numbers import allocate_member_number
from sws_membership.members.models import Member, MemberRole, MemberRoleAssignment
from sws_membership.payments.fake import FakeProcessor
from tests.conftest import make_eligible

YEAR = 2026
TODAY = date(YEAR, 6, 15)


def _member(session, email, roles=()) -> Member:
    member = Member(
        member_number=allocate_member_number(session),
        first_name="Rec",
        last_name="Eipt",
        email=email,
        date_of_birth=date(1990, 1, 1),
        roles=[MemberRoleAssignment(role=r) for r in roles],
    )
    session.add(member)
    session.flush()
    make_eligible(session, member)
    return member


def _sign_in(session, client, member):
    client.cookies.set(SESSION_COOKIE, auth.open_session(session, member))
    client.app.dependency_overrides[current_day] = lambda: TODAY


def _day_pass(session) -> Product:
    load_sample_catalog(session, YEAR)
    return session.scalars(select(Product).where(Product.name == f"Day Pass {YEAR}")).one()


def test_webhook_payment_sends_one_receipt_even_when_redelivered(session, client, mailer):
    member = _member(session, "rec@example.com")
    _sign_in(session, client, member)
    order = client.post("/api/orders", json={"product_ids": [_day_pass(session).id]}).json()
    processor: FakeProcessor = client.app.state.payment_processor
    form = {
        "order_id": str(order["id"]),
        "transaction_id": "tx-receipt",
        "status": "APPROVED",
        "amount_cents": str(order["total_cents"]),
        "checksum": processor.checksum(str(order["id"]), "tx-receipt", "APPROVED"),
    }
    client.post("/api/payments/notification", data=form)
    client.post("/api/payments/notification", data=form)
    receipts = [m for m in mailer.sent if "receipt" in m.subject]
    assert len(receipts) == 1
    assert receipts[0].to == "rec@example.com"
    assert f"Day Pass {YEAR}" in receipts[0].text and "$    35.00" in receipts[0].text
    assert f"order {order['id']}" in receipts[0].subject


def test_declined_payment_sends_no_receipt(session, client, mailer):
    member = _member(session, "nope@example.com")
    _sign_in(session, client, member)
    order = client.post("/api/orders", json={"product_ids": [_day_pass(session).id]}).json()
    processor: FakeProcessor = client.app.state.payment_processor
    form = {
        "order_id": str(order["id"]),
        "transaction_id": "tx-declined",
        "status": "DECLINED",
        "amount_cents": str(order["total_cents"]),
        "checksum": processor.checksum(str(order["id"]), "tx-declined", "DECLINED"),
    }
    client.post("/api/payments/notification", data=form)
    assert [m for m in mailer.sent if "receipt" in m.subject] == []


def test_counter_cash_sale_sends_a_receipt(session, client, mailer):
    staff = _member(session, "staff@example.com", roles=[MemberRole.STAFF])
    buyer = _member(session, "buyer@example.com")
    _sign_in(session, client, staff)
    response = client.post(
        "/api/staff/orders",
        json={
            "member_id": buyer.id,
            "product_ids": [_day_pass(session).id],
            "payment_method": "cash",
        },
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

    client = httpx.Client(
        base_url="https://mandrillapp.com/api/1.0", transport=httpx.MockTransport(handler)
    )
    mailer = MailchimpTransactionalMailer("good-key", "m@example.com", "SWS", client=client)
    mailer.send(EmailMessage(to="a@example.com", subject="Hi", text="hello"))
    assert seen[0].url.path == "/api/1.0/messages/send"
    sent = json.loads(seen[0].read())
    assert sent["key"] == "good-key"
    assert sent["message"]["from_email"] == "m@example.com"
    assert sent["message"]["to"] == [{"email": "a@example.com", "type": "to"}]
    with pytest.raises(MailchimpError):
        mailer.send(EmailMessage(to="bounce@example.com", subject="Hi", text="hello"))
    with pytest.raises(MailchimpError):
        MailchimpTransactionalMailer("refuse-key", "m@example.com", "SWS", client=client).send(
            EmailMessage(to="a@example.com", subject="Hi", text="hello")
        )
