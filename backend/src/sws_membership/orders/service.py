"""Placing an order, paying it, and issuing what it bought."""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from sws_membership.catalog.eligibility import evaluate_basket
from sws_membership.catalog.facts import facts_for
from sws_membership.catalog.models import CURRENCY, Product
from sws_membership.entitlements.models import Entitlement
from sws_membership.members.models import Member
from sws_membership.orders.models import Order, OrderLine, OrderStatus, Payment, PaymentMethod
from sws_membership.payments.processor import PaymentNotification


class OrderRefused(Exception):
    """At least one product is not purchasable by this member today."""

    def __init__(self, reasons: dict[str, list[str]]) -> None:
        super().__init__("; ".join(f"{name}: {', '.join(why)}" for name, why in reasons.items()))
        self.reasons = reasons


class WrongOrderState(Exception):
    """The order is not in a state where this action makes sense."""


def require_pending_card(order: Order) -> None:
    """Only an unpaid card order can be reopened at the processor or cancelled."""
    if order.status is not OrderStatus.PENDING_PAYMENT:
        raise WrongOrderState(f"order {order.id} is {order.status.value}")
    if order.payment_method is not PaymentMethod.CARD:
        raise WrongOrderState(f"order {order.id} is not a card order")


def cancel_order(session: Session, order: Order) -> None:
    """Withdraw an unpaid card order.

    Cancelling records intent only. If the processor still reports an
    approved charge for it afterwards, record_payment pays the order anyway:
    money that was taken must buy what it was taken for.
    """
    require_pending_card(order)
    order.status = OrderStatus.CANCELLED
    session.flush()


@dataclass
class Quote:
    """A basket judged as a whole: the lines it would make and what it refuses."""

    lines: list[OrderLine] = field(default_factory=list)
    refused: dict[str, list[str]] = field(default_factory=dict)

    @property
    def total_cents(self) -> int:
        return sum(line.amount_cents for line in self.lines)


def quote(session: Session, member: Member, product_ids: list[int], day: date) -> Quote:
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
    products = session.scalars(
        select(Product)
        .where(Product.id.in_(product_ids), Product.active.is_(True))
        .options(
            selectinload(Product.prices), selectinload(Product.rules), selectinload(Product.grants)
        )
    ).all()
    found = {product.id: product for product in products}
    missing = [pid for pid in product_ids if pid not in found]
    if missing:
        raise OrderRefused({"order": [f"unknown product {pid}" for pid in missing]})

    ordered = [found[pid] for pid in product_ids]
    results = evaluate_basket(ordered, facts_for(session, member), day)
    quoted = Quote()
    for product in ordered:
        result = results[product.id]
        if not result.purchasable:
            quoted.refused[product.name] = list(result.failures) or ["not on sale today"]
            continue
        quoted.lines.append(
            OrderLine(
                product_id=product.id,
                price_id=result.price.id,
                product_name=product.name,
                amount_cents=result.price.amount_cents,
            )
        )
    return quoted


def place_order(
    session: Session,
    member: Member,
    product_ids: list[int],
    payment_method: PaymentMethod,
    day: date,
    created_by: Member | None = None,
) -> Order:
    """Judge the basket, snapshot prices, and either pay now or await the card."""
    quoted = quote(session, member, product_ids, day)
    if quoted.refused:
        raise OrderRefused(quoted.refused)
    lines = quoted.lines

    order = Order(
        member_id=member.id,
        status=OrderStatus.PENDING_PAYMENT,
        payment_method=payment_method,
        total_cents=quoted.total_cents,
        currency=CURRENCY,
        created_by_member_id=created_by.id if created_by else None,
        lines=lines,
    )
    session.add(order)
    session.flush()
    if payment_method is not PaymentMethod.CARD:
        mark_paid(session, order)
    return order


def mark_paid(session: Session, order: Order, now: datetime | None = None) -> None:
    """Move the order to paid and issue its entitlements, exactly once."""
    if order.status is OrderStatus.PAID:
        return
    order.status = OrderStatus.PAID
    order.paid_at = now or datetime.now(UTC)
    for line in order.lines:
        product = session.get(Product, line.product_id, options=[selectinload(Product.grants)])
        for grant in product.grants:
            session.add(
                Entitlement(
                    member_id=order.member_id,
                    kind=grant.kind,
                    product_id=product.id,
                    valid_from=grant.valid_from,
                    valid_to=grant.valid_to,
                    visits_remaining=grant.visit_count,
                )
            )
    session.flush()


def record_payment(
    session: Session, processor_name: str, notification: PaymentNotification
) -> tuple[Payment, bool]:
    """Store a verified notification; the first approved one pays the order.

    Returns the payment and whether this call moved the order to paid. A
    notification seen before (same processor and transaction) is returned
    unchanged with False, so a processor that retries delivery changes
    nothing and triggers nothing.
    """
    existing = session.scalars(
        select(Payment).where(
            Payment.processor == processor_name,
            Payment.transaction_id == notification.transaction_id,
        )
    ).first()
    if existing is not None:
        return existing, False
    order = session.get(Order, notification.order_id)
    if order is None:
        raise LookupError(f"no order {notification.order_id}")
    payment = Payment(
        order_id=order.id,
        processor=processor_name,
        transaction_id=notification.transaction_id,
        approved=notification.approved,
        amount_cents=notification.amount_cents,
        raw_notification=notification.raw,
    )
    session.add(payment)
    paid_now = False
    if (
        notification.approved
        and notification.amount_cents == order.total_cents
        and order.status is not OrderStatus.PAID
    ):
        mark_paid(session, order)
        paid_now = True
    session.flush()
    return payment, paid_now
