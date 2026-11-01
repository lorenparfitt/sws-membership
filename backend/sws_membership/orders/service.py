"""Placing an order, paying it, and issuing what it bought."""

from dataclasses import dataclass, field
from datetime import date, datetime

from django.db import transaction
from django.utils import timezone

from sws_membership.catalog.eligibility import evaluate_basket
from sws_membership.catalog.facts import facts_for
from sws_membership.catalog.models import CURRENCY, Product
from sws_membership.entitlements.models import Entitlement
from sws_membership.errors import Refused
from sws_membership.members.models import Member
from sws_membership.orders.models import (
    Order,
    OrderLine,
    OrderStatus,
    Payment,
    PaymentMethod,
    Refund,
)
from sws_membership.payments.processor import PaymentNotification, PaymentProcessor


class OrderRefused(Refused):
    """At least one product is not purchasable by this member today."""


class WrongOrderState(Exception):
    """The order is not in a state where this action makes sense."""


class RefundDeclined(Exception):
    """The processor would not return the money; nothing was changed."""


@dataclass
class Quote:
    """A basket judged as a whole: the lines it would make and what it refuses."""

    lines: list[OrderLine] = field(default_factory=list)
    refused: dict[str, list[str]] = field(default_factory=dict)

    @property
    def total_cents(self) -> int:
        return sum(line.amount_cents for line in self.lines)


def quote(member: Member, product_ids: list[int], day: date) -> Quote:
    """Price a basket, counting what each product would grant toward the others.

    Raises OrderRefused when the basket itself is malformed: empty, a product
    listed twice (every product is bought once; a multi-visit pass is its
    own product), or a product that does not exist or is retired. Refusals
    of eligible products are reported per product in the quote.
    """
    if not product_ids:
        raise OrderRefused({"order": ["nothing selected"]})
    repeated = sorted({pid for pid in product_ids if product_ids.count(pid) > 1})
    if repeated:
        raise OrderRefused({"order": [f"product {pid} listed twice" for pid in repeated]})
    found = {
        p.id: p
        for p in Product.objects.filter(id__in=product_ids, active=True).prefetch_related(
            "prices", "rules", "grants"
        )
    }
    missing = [pid for pid in product_ids if pid not in found]
    if missing:
        raise OrderRefused({"order": [f"unknown product {pid}" for pid in missing]})

    ordered = [found[pid] for pid in product_ids]
    specs = [p.spec() for p in ordered]
    results = evaluate_basket(specs, facts_for(member), day)
    quoted = Quote()
    for product, spec in zip(ordered, specs, strict=True):
        result = results[spec.id]
        if not result.purchasable:
            quoted.refused[product.name] = list(result.failures) or ["not on sale today"]
            continue
        quoted.lines.append(
            OrderLine(
                product=product,
                price_id=result.price.id,
                product_name=product.name,
                amount_cents=result.price.amount_cents,
            )
        )
    return quoted


@transaction.atomic
def place_order(
    member: Member,
    product_ids: list[int],
    payment_method: PaymentMethod,
    day: date,
    created_by: Member | None = None,
) -> Order:
    """Judge the basket, snapshot prices, and either pay now or await the card."""
    quoted = quote(member, product_ids, day)
    if quoted.refused:
        raise OrderRefused(quoted.refused)
    order = Order.objects.create(
        member=member,
        status=OrderStatus.PENDING_PAYMENT,
        payment_method=payment_method,
        total_cents=quoted.total_cents,
        currency=CURRENCY,
        created_by=created_by,
    )
    for line in quoted.lines:
        line.order = order
    OrderLine.objects.bulk_create(quoted.lines)
    if payment_method != PaymentMethod.CARD:
        mark_paid(order)
    return order


def mark_paid(order: Order, now: datetime | None = None) -> None:
    """Move the order to paid and issue its entitlements, exactly once."""
    if order.status == OrderStatus.PAID:
        return
    order.status = OrderStatus.PAID
    order.paid_at = now or timezone.now()
    order.save(update_fields=["status", "paid_at"])
    rows = []
    for line in order.lines.select_related("product").prefetch_related("product__grants"):
        for grant in line.product.grants.all():
            rows.append(
                Entitlement(
                    member_id=order.member_id,
                    kind=grant.kind,
                    product=line.product,
                    order_line=line,
                    valid_from=grant.valid_from,
                    valid_to=grant.valid_to,
                    visits_remaining=grant.visit_count,
                )
            )
    Entitlement.objects.bulk_create(rows)


def require_pending_card(order: Order) -> None:
    """Only an unpaid card order can be reopened at the processor or cancelled."""
    if order.status != OrderStatus.PENDING_PAYMENT:
        raise WrongOrderState(f"order {order.id} is {order.status}")
    if order.payment_method != PaymentMethod.CARD:
        raise WrongOrderState(f"order {order.id} is not a card order")


def cancel_order(order: Order) -> None:
    """Withdraw an unpaid card order.

    Cancelling records intent only. If the processor still reports an
    approved charge for it afterwards, record_payment pays the order anyway:
    money that was taken must buy what it was taken for.
    """
    require_pending_card(order)
    order.status = OrderStatus.CANCELLED
    order.save(update_fields=["status"])


def refund_order(order: Order, by: Member, reason: str, processor: PaymentProcessor) -> Refund:
    """Give the whole order back and withdraw what it bought.

    A pass is one unit, so an order is refunded whole, never a line or a
    partial amount. A card order is refunded through the processor against
    the payment that paid it, and only an approved answer changes anything
    here. Cash and free orders are recorded only: the money changes hands
    at the counter.
    """
    if order.status != OrderStatus.PAID:
        raise WrongOrderState(f"order {order.id} is {order.status}")
    payment = None
    result = None
    if order.payment_method == PaymentMethod.CARD:
        payment = (
            order.payments.filter(approved=True, amount_cents=order.total_cents)
            .order_by("received_at", "id")
            .first()
        )
        if payment is None:
            raise WrongOrderState(f"order {order.id} has no approved card payment on record")
        result = processor.refund(
            payment.transaction_id, order.total_cents, order.currency, str(order.id)
        )
        if not result.approved:
            raise RefundDeclined(result.reason or "the processor declined the refund")
    with transaction.atomic():
        refund = Refund.objects.create(
            order=order,
            payment=payment,
            amount_cents=order.total_cents,
            processor=result.processor if result else "",
            transaction_id=result.transaction_id if result else "",
            raw_response=result.raw if result else {},
            reason=reason,
            refunded_by=by,
        )
        order.status = OrderStatus.REFUNDED
        order.save(update_fields=["status"])
        Entitlement.objects.filter(order_line__order=order, revoked_at__isnull=True).update(
            revoked_at=refund.refunded_at
        )
    return refund


@transaction.atomic
def record_payment(processor_name: str, notification: PaymentNotification) -> tuple[Payment, bool]:
    """Store a verified notification; the first approved one pays the order.

    Returns the payment and whether this call moved the order to paid. A
    notification seen before (same processor and transaction) is returned
    unchanged with False, so a processor that retries delivery changes
    nothing and triggers nothing.
    """
    existing = Payment.objects.filter(
        processor=processor_name, transaction_id=notification.transaction_id
    ).first()
    if existing is not None:
        return existing, False
    order = Order.objects.filter(id=notification.order_id).first()
    if order is None:
        raise LookupError(f"no order {notification.order_id}")
    payment = Payment.objects.create(
        order=order,
        processor=processor_name,
        transaction_id=notification.transaction_id,
        approved=notification.approved,
        amount_cents=notification.amount_cents,
        raw_notification=notification.raw,
    )
    paid_now = False
    if (
        notification.approved
        and notification.amount_cents == order.total_cents
        and order.status != OrderStatus.PAID
    ):
        mark_paid(order)
        paid_now = True
    return payment, paid_now
