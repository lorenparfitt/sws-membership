"""Development only: approve a card order as the fake processor would.

Mounted by main only when the fake processor is configured, so the route
does not exist in production. It goes through the same verification and
recording path as a real notification; nothing is short-circuited.
"""

from fastapi import APIRouter, HTTPException, Request, status

from sws_membership.auth.dependencies import CurrentMember, DatabaseSession
from sws_membership.orders import service
from sws_membership.orders.models import Order
from sws_membership.payments.fake import FakeProcessor

router = APIRouter(prefix="/api/payments/fake", tags=["payments-fake"])


@router.post("/approve/{order_id}")
def approve(
    order_id: int, request: Request, session: DatabaseSession, member: CurrentMember
) -> dict:
    processor: FakeProcessor = request.app.state.payment_processor
    order = session.get(Order, order_id)
    if order is None or order.member_id != member.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such order")
    transaction_id = f"fake-{order_id}-{len(order.payments) + 1}"
    form = {
        "order_id": str(order_id),
        "transaction_id": transaction_id,
        "status": "APPROVED",
        "amount_cents": str(order.total_cents),
        "currency": order.currency,
    }
    form["checksum"] = processor.checksum(form["order_id"], transaction_id, "APPROVED")
    notification = processor.verify_notification(form)
    service.record_payment(session, processor.name, notification)
    return {"status": order.status.value}
