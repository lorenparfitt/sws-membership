"""Buying online, ringing up at the Spit, and the processor's notification."""

from datetime import datetime

from django.http import HttpResponse
from ninja import Router, Schema, Status
from ninja.errors import HttpError

from sws_membership import clock
from sws_membership.accounts.auth import member_auth, staff_auth
from sws_membership.catalog.models import CURRENCY
from sws_membership.members.api import load_member
from sws_membership.members.models import Member
from sws_membership.orders import service
from sws_membership.orders.models import Order, OrderStatus, PaymentMethod
from sws_membership.orders.receipts import receipt_text, send_receipt
from sws_membership.payments.processor import NotificationRejected
from sws_membership.wiring import wiring

router = Router(tags=["orders"])


class NewOrder(Schema):
    product_ids: list[int]


class StaffQuote(NewOrder):
    member_id: int


class StaffOrder(StaffQuote):
    payment_method: PaymentMethod


class LineView(Schema):
    product_name: str
    amount_cents: int


class QuoteLineView(LineView):
    product_id: int


class QuoteView(Schema):
    """A basket priced as a whole, before any order exists."""

    lines: list[QuoteLineView]
    refused: dict[str, list[str]]
    total_cents: int
    currency: str

    @classmethod
    def of(cls, quoted: service.Quote) -> "QuoteView":
        return cls(
            lines=[
                QuoteLineView(
                    product_id=l.product_id,
                    product_name=l.product_name,
                    amount_cents=l.amount_cents,
                )
                for l in quoted.lines
            ],
            refused=quoted.refused,
            total_cents=quoted.total_cents,
            currency=CURRENCY,
        )


class CheckoutView(Schema):
    processor: str
    session_token: str
    parameters: dict[str, str]


class OrderView(Schema):
    id: int
    status: str
    payment_method: str
    total_cents: int
    currency: str
    created_at: datetime
    paid_at: datetime | None
    lines: list[LineView]
    checkout: CheckoutView | None = None

    @classmethod
    def of(cls, order: Order, checkout=None) -> "OrderView":
        return cls(
            id=order.id,
            status=order.status,
            payment_method=order.payment_method,
            total_cents=order.total_cents,
            currency=order.currency,
            created_at=order.created_at,
            paid_at=order.paid_at,
            lines=[
                LineView(product_name=l.product_name, amount_cents=l.amount_cents)
                for l in order.lines.all()
            ],
            checkout=CheckoutView(**checkout.__dict__) if checkout else None,
        )


def _wrong_state(problem: service.WrongOrderState) -> HttpError:
    return HttpError(409, str(problem))


def _orders_of(member_id: int) -> list[Order]:
    return list(Order.objects.filter(member_id=member_id).prefetch_related("lines"))


def _own_order(member: Member, order_id: int) -> Order:
    order = Order.objects.filter(id=order_id, member=member).first()
    if order is None:
        raise HttpError(404, "no such order")
    return order


def _any_order(order_id: int) -> Order:
    order = Order.objects.filter(id=order_id).first()
    if order is None:
        raise HttpError(404, "no such order")
    return order


def _receipt(order: Order) -> HttpResponse:
    if order.status != OrderStatus.PAID:
        raise HttpError(409, f"order {order.id} is not paid")
    return HttpResponse(receipt_text(order, order.member), content_type="text/plain; charset=utf-8")


def _reopen(order: Order) -> OrderView:
    """A fresh processor session for an order whose form was closed or lost."""
    try:
        service.require_pending_card(order)
    except service.WrongOrderState as problem:
        raise _wrong_state(problem)
    checkout = wiring.processor.open_checkout(order.id, order.total_cents, order.currency)
    return OrderView.of(order, checkout)


def _cancel(order: Order) -> OrderView:
    try:
        service.cancel_order(order)
    except service.WrongOrderState as problem:
        raise _wrong_state(problem)
    return OrderView.of(order)


# --- the member's own orders -------------------------------------------------


@router.post("/orders/quote", auth=member_auth, response=QuoteView)
def quote_basket(request, body: NewOrder):
    return QuoteView.of(service.quote(request.auth, body.product_ids, clock.today()))


@router.post("/orders", auth=member_auth, response={201: OrderView})
def place_order(request, body: NewOrder):
    order = service.place_order(request.auth, body.product_ids, PaymentMethod.CARD, clock.today())
    checkout = wiring.processor.open_checkout(order.id, order.total_cents, order.currency)
    return Status(201, OrderView.of(order, checkout))


@router.get("/orders", auth=member_auth, response=list[OrderView])
def my_orders(request):
    return [OrderView.of(order) for order in _orders_of(request.auth.id)]


@router.get("/orders/{order_id}", auth=member_auth, response=OrderView)
def order_status(request, order_id: int):
    return OrderView.of(_own_order(request.auth, order_id))


@router.get("/orders/{order_id}/receipt", auth=member_auth)
def my_receipt(request, order_id: int):
    return _receipt(_own_order(request.auth, order_id))


@router.post("/orders/{order_id}/checkout", auth=member_auth, response=OrderView)
def reopen_checkout(request, order_id: int):
    return _reopen(_own_order(request.auth, order_id))


@router.post("/orders/{order_id}/cancel", auth=member_auth, response=OrderView)
def cancel_order(request, order_id: int):
    return _cancel(_own_order(request.auth, order_id))


# --- the till ---------------------------------------------------------------


@router.post("/staff/orders/quote", auth=staff_auth, response=QuoteView)
def staff_quote_basket(request, body: StaffQuote):
    member = load_member(body.member_id)
    return QuoteView.of(service.quote(member, body.product_ids, clock.today()))


@router.post("/staff/orders", auth=staff_auth, response={201: OrderView})
def staff_order(request, body: StaffOrder):
    """Ring up any member. Cash and free pay at once; card opens the processor form.

    The card form is the processor's own, shown to the member at the counter,
    so card details never pass through staff hands or this API.
    """
    member = load_member(body.member_id)
    order = service.place_order(
        member, body.product_ids, body.payment_method, clock.today(), created_by=request.auth
    )
    checkout = None
    if body.payment_method == PaymentMethod.CARD:
        checkout = wiring.processor.open_checkout(order.id, order.total_cents, order.currency)
    elif order.status == OrderStatus.PAID:
        send_receipt(wiring.mailer, order, member)
    return Status(201, OrderView.of(order, checkout))


@router.get("/staff/orders/{order_id}", auth=staff_auth, response=OrderView)
def staff_order_status(request, order_id: int):
    return OrderView.of(_any_order(order_id))


@router.get("/staff/orders/{order_id}/receipt", auth=staff_auth)
def staff_receipt(request, order_id: int):
    return _receipt(_any_order(order_id))


@router.post("/staff/orders/{order_id}/checkout", auth=staff_auth, response=OrderView)
def staff_reopen_checkout(request, order_id: int):
    return _reopen(_any_order(order_id))


@router.post("/staff/orders/{order_id}/cancel", auth=staff_auth, response=OrderView)
def staff_cancel_order(request, order_id: int):
    return _cancel(_any_order(order_id))


# --- the processor's webhook -------------------------------------------------


@router.post("/payments/notification", auth=None, include_in_schema=False)
def payment_notification(request):
    """The processor's webhook. Form encoded; answers OK once stored."""
    form = {key: str(value) for key, value in request.POST.items()}
    processor = wiring.processor
    try:
        notification = processor.verify_notification(form)
        payment, paid_now = service.record_payment(processor.name, notification)
    except NotificationRejected as why:
        raise HttpError(400, str(why))
    except LookupError as why:
        raise HttpError(404, str(why))
    if paid_now:
        send_receipt(wiring.mailer, payment.order, payment.order.member)
    return HttpResponse("OK", content_type="text/plain")
