"""Buying online, ringing up at the Spit, and the processor's notification."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from sws_membership.auth.dependencies import (
    CurrentMember,
    DatabaseSession,
    MailerDependency,
    require_role,
)
from sws_membership.catalog.router import CurrentDay
from sws_membership.members.models import Member, MemberRole
from sws_membership.orders import service
from sws_membership.orders.models import Order, OrderStatus, PaymentMethod
from sws_membership.orders.receipts import send_receipt
from sws_membership.payments.processor import NotificationRejected, PaymentProcessor

router = APIRouter(prefix="/api", tags=["orders"])


def get_processor(request: Request) -> PaymentProcessor:
    return request.app.state.payment_processor


Processor = Annotated[PaymentProcessor, Depends(get_processor)]


class NewOrder(BaseModel):
    product_ids: list[int]


class StaffOrder(NewOrder):
    member_id: int
    payment_method: PaymentMethod


class LineView(BaseModel):
    product_name: str
    amount_cents: int


class CheckoutView(BaseModel):
    processor: str
    session_token: str
    parameters: dict[str, str]


class OrderView(BaseModel):
    id: int
    status: str
    payment_method: str
    total_cents: int
    currency: str
    lines: list[LineView]
    checkout: CheckoutView | None = None

    @classmethod
    def of(cls, order: Order, checkout=None) -> "OrderView":
        return cls(
            id=order.id,
            status=order.status.value,
            payment_method=order.payment_method.value,
            total_cents=order.total_cents,
            currency=order.currency,
            lines=[
                LineView(product_name=l.product_name, amount_cents=l.amount_cents)
                for l in order.lines
            ],
            checkout=CheckoutView(**checkout.__dict__) if checkout else None,
        )


def _refused(problem: service.OrderRefused) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, {"refused": problem.reasons})


@router.post("/orders", status_code=status.HTTP_201_CREATED)
def place_order(
    body: NewOrder,
    session: DatabaseSession,
    member: CurrentMember,
    today: CurrentDay,
    processor: Processor,
) -> OrderView:
    try:
        order = service.place_order(session, member, body.product_ids, PaymentMethod.CARD, today)
    except service.OrderRefused as problem:
        raise _refused(problem)
    checkout = processor.open_checkout(order.id, order.total_cents, order.currency)
    return OrderView.of(order, checkout)


@router.get("/orders/{order_id}")
def order_status(order_id: int, session: DatabaseSession, member: CurrentMember) -> OrderView:
    order = session.get(Order, order_id)
    if order is None or order.member_id != member.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such order")
    return OrderView.of(order)


StaffMember = Annotated[Member, Depends(require_role(MemberRole.STAFF))]


@router.post("/staff/orders", status_code=status.HTTP_201_CREATED)
def staff_order(
    body: StaffOrder,
    session: DatabaseSession,
    today: CurrentDay,
    staff: StaffMember,
    processor: Processor,
    mailer: MailerDependency,
) -> OrderView:
    """Ring up any member. Cash and free pay at once; card opens the processor form.

    The card form is the processor's own, shown to the member at the counter,
    so card details never pass through staff hands or this API.
    """
    member = session.get(Member, body.member_id)
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such member")
    try:
        order = service.place_order(
            session, member, body.product_ids, body.payment_method, today, created_by=staff
        )
    except service.OrderRefused as problem:
        raise _refused(problem)
    checkout = None
    if body.payment_method is PaymentMethod.CARD:
        checkout = processor.open_checkout(order.id, order.total_cents, order.currency)
    elif order.status is OrderStatus.PAID:
        send_receipt(mailer, order, member)
    return OrderView.of(order, checkout)


@router.get("/staff/orders/{order_id}")
def staff_order_status(order_id: int, session: DatabaseSession, staff: StaffMember) -> OrderView:
    order = session.get(Order, order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such order")
    return OrderView.of(order)


@router.post("/payments/notification", include_in_schema=False)
async def payment_notification(
    request: Request, session: DatabaseSession, processor: Processor, mailer: MailerDependency
) -> str:
    """The processor's webhook. Form encoded; answers OK once stored."""
    form = {key: str(value) for key, value in (await request.form()).items()}
    try:
        notification = processor.verify_notification(form)
        payment, paid_now = service.record_payment(session, processor.name, notification)
        if paid_now:
            send_receipt(mailer, payment.order, session.get(Member, payment.order.member_id))
    except NotificationRejected as why:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(why))
    except LookupError as why:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(why))
    return "OK"


__all__ = ["OrderStatus", "router"]
