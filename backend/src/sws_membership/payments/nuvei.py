"""Nuvei through its Simply Connect flow.

The server calls openOrder with a SHA-256 checksum and hands the returned
sessionToken to the browser, which renders Nuvei's checkout form. Nuvei then
posts a Direct Merchant Notification (DMN), form encoded, whose
advanceResponseChecksum is SHA-256 over the secret key and six fields. Only
a verified DMN moves an order to paid.

Checksum rules and field names follow the Nuvei documentation pages on
authentication and payment DMNs. Both are pure functions here so they are
tested against the documented worked example.
"""

import hashlib
from datetime import UTC, datetime

import httpx

from sws_membership.payments.processor import (
    CheckoutSession,
    NotificationRejected,
    PaymentNotification,
)

HOSTS = {
    "int": "https://ppp-test.nuvei.com",
    "prod": "https://secure.safecharge.com",
}
OPEN_ORDER_PATH = "/ppp/api/v1/openOrder.do"
APPROVED_STATUSES = {"APPROVED", "SUCCESS"}
PAYMENT_TRANSACTION_TYPES = {"Sale", "Auth"}


def open_order_checksum(
    merchant_id: str,
    merchant_site_id: str,
    client_request_id: str,
    amount: str,
    currency: str,
    time_stamp: str,
    secret_key: str,
) -> str:
    """Fields concatenated in request order with no separators, then SHA-256."""
    joined = f"{merchant_id}{merchant_site_id}{client_request_id}{amount}{currency}{time_stamp}{secret_key}"
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def notification_checksum(
    secret_key: str,
    total_amount: str,
    currency: str,
    response_time_stamp: str,
    ppp_transaction_id: str,
    status: str,
    product_id: str,
) -> str:
    """Secret first, then the six DMN fields in documented order, SHA-256."""
    joined = (
        f"{secret_key}{total_amount}{currency}{response_time_stamp}"
        f"{ppp_transaction_id}{status}{product_id}"
    )
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def format_amount(amount_cents: int) -> str:
    return f"{amount_cents // 100}.{amount_cents % 100:02d}"


class NuveiError(Exception):
    pass


class NuveiProcessor:
    name = "nuvei"

    def __init__(
        self,
        merchant_id: str,
        merchant_site_id: str,
        secret_key: str,
        environment: str,
        notification_url: str,
        client: httpx.Client | None = None,
    ) -> None:
        self.merchant_id = merchant_id
        self.merchant_site_id = merchant_site_id
        self.secret_key = secret_key
        self.environment = environment
        self.notification_url = notification_url
        self.client = client or httpx.Client(base_url=HOSTS[environment], timeout=15)

    def open_checkout(self, order_id: int, amount_cents: int, currency: str) -> CheckoutSession:
        amount = format_amount(amount_cents)
        time_stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        client_request_id = f"order-{order_id}-{time_stamp}"
        body = {
            "merchantId": self.merchant_id,
            "merchantSiteId": self.merchant_site_id,
            "clientRequestId": client_request_id,
            "clientUniqueId": str(order_id),
            "amount": amount,
            "currency": currency,
            "timeStamp": time_stamp,
            "urlDetails": {"notificationUrl": self.notification_url},
            "checksum": open_order_checksum(
                self.merchant_id,
                self.merchant_site_id,
                client_request_id,
                amount,
                currency,
                time_stamp,
                self.secret_key,
            ),
        }
        response = self.client.post(OPEN_ORDER_PATH, json=body)
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "SUCCESS" or not payload.get("sessionToken"):
            raise NuveiError(f"openOrder failed: {payload.get('reason') or payload}")
        return CheckoutSession(
            processor=self.name,
            session_token=payload["sessionToken"],
            parameters={
                "env": self.environment,
                "merchantId": self.merchant_id,
                "merchantSiteId": self.merchant_site_id,
                "currency": currency,
                "amount": amount,
            },
        )

    def verify_notification(self, form: dict[str, str]) -> PaymentNotification:
        try:
            transaction_id = form.get("PPP_TransactionID") or form["PPP_TransactionId"]
            expected = notification_checksum(
                self.secret_key,
                form["totalAmount"],
                form["currency"],
                form["responseTimeStamp"],
                transaction_id,
                form["Status"],
                form.get("productId", "").replace("+", " "),
            )
            presented = form["advanceResponseChecksum"]
            order_reference = form.get("clientUniqueId") or form["merchant_unique_id"]
        except KeyError as missing:
            raise NotificationRejected(f"missing {missing}") from None
        if presented.lower() != expected:
            raise NotificationRejected("checksum mismatch")
        if form.get("transactionType", "Sale") not in PAYMENT_TRANSACTION_TYPES:
            raise NotificationRejected(f"not a payment: {form.get('transactionType')}")
        try:
            order_id = int(order_reference)
        except ValueError:
            raise NotificationRejected(f"order reference {order_reference!r} is not ours") from None
        dollars, _, cents = form["totalAmount"].partition(".")
        amount_cents = int(dollars) * 100 + int((cents + "00")[:2])
        return PaymentNotification(
            order_id=order_id,
            transaction_id=transaction_id,
            approved=form["Status"] in APPROVED_STATUSES,
            amount_cents=amount_cents,
            currency=form["currency"],
            raw=dict(form),
        )
