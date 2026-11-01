"""Nuvei checksum rules, checked against the worked example in its docs."""

import json

import httpx
import pytest

from sws_membership.payments.nuvei import (
    REFUND_PATH,
    NuveiProcessor,
    format_amount,
    notification_checksum,
    open_order_checksum,
    refund_checksum,
    scrub_card_fields,
)
from sws_membership.payments.processor import NotificationIgnored, NotificationRejected


def test_open_order_checksum_matches_the_documented_example():
    # docs.nuvei.com authentication page: the example omits clientRequestId.
    assert (
        open_order_checksum(
            "2389668057520747493", "199116", "", "", "EUR", "20200101131211", "Secret1234"
        )
        == "5330e3b909af965d6c78136a1d363f32e07626a27736f8dcc1ee2a5ac2e2eeec"
    )


def test_amounts_are_formatted_as_dollars_and_cents():
    assert format_amount(4000) == "40.00"
    assert format_amount(2505) == "25.05"
    assert format_amount(7) == "0.07"


def _processor() -> NuveiProcessor:
    return NuveiProcessor("m", "s", "topsecret", "int", "http://x/notify", client=object())


def _dmn(**overrides) -> dict[str, str]:
    form = {
        "totalAmount": "40.00",
        "currency": "CAD",
        "responseTimeStamp": "2026-06-15.12:00:00",
        "PPP_TransactionID": "111222333",
        "Status": "APPROVED",
        "productId": "Adult+SWS+Membership",
        "clientUniqueId": "42",
        "transactionType": "Sale",
    }
    form.update(overrides)
    form.setdefault(
        "advanceResponseChecksum",
        notification_checksum(
            "topsecret",
            form["totalAmount"],
            form["currency"],
            form["responseTimeStamp"],
            form["PPP_TransactionID"],
            form["Status"],
            form["productId"].replace("+", " "),
        ),
    )
    return form


def test_a_genuine_notification_is_accepted_and_decoded():
    result = _processor().verify_notification(_dmn())
    assert (result.order_id, result.transaction_id, result.approved) == (42, "111222333", True)
    assert (result.amount_cents, result.currency) == (4000, "CAD")


def test_a_declined_notification_is_verified_but_not_approved():
    assert _processor().verify_notification(_dmn(Status="DECLINED")).approved is False


def test_a_tampered_amount_fails_the_checksum():
    form = _dmn()
    form["totalAmount"] = "0.01"
    with pytest.raises(NotificationRejected):
        _processor().verify_notification(form)


def test_a_notification_signed_with_another_secret_is_rejected():
    form = _dmn()
    form["advanceResponseChecksum"] = notification_checksum(
        "wrong",
        "40.00",
        "CAD",
        "2026-06-15.12:00:00",
        "111222333",
        "APPROVED",
        "Adult SWS Membership",
    )
    with pytest.raises(NotificationRejected):
        _processor().verify_notification(form)


def test_non_payment_transaction_types_are_acknowledged_but_not_recorded():
    """A refund we asked for comes back as a Credit DMN: genuine, not a payment."""
    with pytest.raises(NotificationIgnored):
        _processor().verify_notification(_dmn(transactionType="Credit"))


def test_a_non_payment_type_still_has_to_pass_the_checksum():
    form = _dmn(transactionType="Credit")
    form["advanceResponseChecksum"] = "0" * 64
    with pytest.raises(NotificationRejected):
        _processor().verify_notification(form)


def test_a_foreign_order_reference_is_rejected():
    with pytest.raises(NotificationRejected):
        _processor().verify_notification(_dmn(clientUniqueId="not-ours"))


def test_card_fields_never_reach_the_stored_notification():
    form = _dmn(
        cardNumber="4****1111",
        cardCompany="Visa",
        expMonth="12",
        expYear="2030",
        nameOnCard="S Tester",
        bin="411111",
        ccToken="tok_abc",
    )
    result = _processor().verify_notification(form)
    kept = set(result.raw)
    assert {
        "cardNumber",
        "cardCompany",
        "expMonth",
        "expYear",
        "nameOnCard",
        "bin",
        "ccToken",
    }.isdisjoint(kept)
    assert {"totalAmount", "currency", "Status", "PPP_TransactionID", "clientUniqueId"} <= kept
    assert scrub_card_fields({"currency": "CAD", "clientRequestId": "x"}) == {
        "currency": "CAD",
        "clientRequestId": "x",
    }


def _refund_client(answer: dict, seen: list[dict]) -> httpx.Client:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == REFUND_PATH
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=answer)

    return httpx.Client(
        base_url="https://ppp-test.nuvei.com", transport=httpx.MockTransport(handle)
    )


def test_a_refund_request_names_the_sale_and_signs_the_documented_fields():
    seen: list[dict] = []
    answer = {
        "status": "SUCCESS",
        "transactionStatus": "APPROVED",
        "transactionId": "2110000000009",
        "gwErrorCode": 0,
        "reason": "",
    }
    processor = NuveiProcessor(
        "m", "s", "topsecret", "int", "http://x/notify", client=_refund_client(answer, seen)
    )
    result = processor.refund("111222333", 6500, "CAD", "42")
    assert result.approved and result.transaction_id == "2110000000009"
    assert result.processor == "nuvei" and result.reason == ""
    body = seen[0]
    assert (body["relatedTransactionId"], body["amount"], body["currency"]) == (
        "111222333",
        "65.00",
        "CAD",
    )
    assert body["clientUniqueId"] == "42"
    assert body["checksum"] == refund_checksum(
        "m",
        "s",
        body["clientRequestId"],
        "42",
        "65.00",
        "CAD",
        "111222333",
        body["timeStamp"],
        "topsecret",
    )


def test_a_refund_the_gateway_declines_carries_its_reason():
    answer = {
        "status": "SUCCESS",
        "transactionStatus": "DECLINED",
        "transactionId": "2110000000010",
        "gwErrorCode": -1,
        "gwErrorReason": "Transaction already refunded",
    }
    processor = NuveiProcessor(
        "m", "s", "topsecret", "int", "http://x/notify", client=_refund_client(answer, [])
    )
    result = processor.refund("111222333", 6500, "CAD", "42")
    assert result.approved is False
    assert result.reason == "Transaction already refunded"
