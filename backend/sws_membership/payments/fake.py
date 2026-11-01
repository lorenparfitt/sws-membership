"""A processor for development and tests: no network, and approval is a form post.

The notification carries a checksum over a shared secret so the webhook path
is exercised the same way as with a real processor, including rejection of
a forged post.
"""

import hashlib

from sws_membership.payments.processor import (
    CheckoutSession,
    NotificationRejected,
    PaymentNotification,
    RefundResult,
)


class FakeProcessor:
    name = "fake"

    def __init__(self, secret: str = "fake-secret") -> None:
        self.secret = secret
        self.refunds: list[RefundResult] = []

    def open_checkout(self, order_id: int, amount_cents: int, currency: str) -> CheckoutSession:
        return CheckoutSession(
            processor=self.name,
            session_token=f"fake-session-{order_id}",
            parameters={"amount_cents": str(amount_cents), "currency": currency},
        )

    def checksum(self, order_id: str, transaction_id: str, status: str) -> str:
        return hashlib.sha256(
            f"{self.secret}{order_id}{transaction_id}{status}".encode()
        ).hexdigest()

    def verify_notification(self, form: dict[str, str]) -> PaymentNotification:
        try:
            order_id, transaction_id, status = (
                form["order_id"],
                form["transaction_id"],
                form["status"],
            )
        except KeyError as missing:
            raise NotificationRejected(f"missing {missing}") from None
        if form.get("checksum") != self.checksum(order_id, transaction_id, status):
            raise NotificationRejected("bad checksum")
        return PaymentNotification(
            order_id=int(order_id),
            transaction_id=transaction_id,
            approved=status == "APPROVED",
            amount_cents=int(form.get("amount_cents", "0")),
            currency=form.get("currency", "CAD"),
            raw=dict(form),
        )

    def refund(
        self, transaction_id: str, amount_cents: int, currency: str, reference: str
    ) -> RefundResult:
        result = RefundResult(
            processor=self.name,
            transaction_id=f"refund-of-{transaction_id}",
            approved=True,
            raw={
                "relatedTransactionId": transaction_id,
                "amount_cents": str(amount_cents),
                "currency": currency,
                "reference": reference,
            },
        )
        self.refunds.append(result)
        return result
