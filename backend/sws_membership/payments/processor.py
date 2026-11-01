"""The one seam between orders and whoever charges the card.

A processor opens a checkout for an order and verifies the notification it
later posts back. The order code never sees processor specifics, so a
processor change touches one module and the wiring that picks it.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CheckoutSession:
    """What the browser needs to render the processor's payment form."""

    processor: str
    session_token: str
    parameters: dict[str, str]


@dataclass(frozen=True)
class PaymentNotification:
    """A verified notification: which order, which transaction, what happened."""

    order_id: int
    transaction_id: str
    approved: bool
    amount_cents: int
    currency: str
    raw: dict[str, str]


@dataclass(frozen=True)
class RefundResult:
    """The processor's answer to a refund request."""

    processor: str
    transaction_id: str
    approved: bool
    raw: dict[str, str]
    reason: str = ""


class NotificationRejected(Exception):
    """The notification failed verification and must be ignored."""


class NotificationIgnored(Exception):
    """A genuine notification about something other than a payment, such as
    the processor confirming a refund we asked for. Acknowledged, not recorded."""


class PaymentProcessor(Protocol):
    name: str

    def open_checkout(self, order_id: int, amount_cents: int, currency: str) -> CheckoutSession: ...

    def verify_notification(self, form: dict[str, str]) -> PaymentNotification: ...

    def refund(
        self, transaction_id: str, amount_cents: int, currency: str, reference: str
    ) -> RefundResult: ...
