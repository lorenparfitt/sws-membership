"""Development only: approve a card order as the fake processor would.

Mounted only when the fake processor is configured, so the route does not
exist in production. It goes through the same verification and recording
path as a real notification; nothing is short-circuited.
"""

from ninja import Router
from ninja.errors import HttpError

from sws_membership.accounts.auth import member_auth
from sws_membership.members.models import MemberRole
from sws_membership.orders import service
from sws_membership.orders.models import Order
from sws_membership.orders.receipts import send_receipt
from sws_membership.payments.fake import FakeProcessor
from sws_membership.wiring import wiring

router = Router(tags=["payments-fake"])


@router.post("/approve/{order_id}", auth=member_auth)
def approve(request, order_id: int) -> dict:
    """Development only: approve a card order as the fake processor would."""
    processor = wiring.processor
    if not isinstance(processor, FakeProcessor):
        raise HttpError(404, "not available with this payment processor")
    member = request.auth
    order = Order.objects.filter(id=order_id).select_related("member").first()
    is_staff = member.has_role(MemberRole.STAFF) or member.has_role(MemberRole.ADMIN)
    if order is None or (order.member_id != member.id and not is_staff):
        raise HttpError(404, "no such order")
    transaction_id = f"fake-{order_id}-{order.payments.count() + 1}"
    form = {
        "order_id": str(order_id),
        "transaction_id": transaction_id,
        "status": "APPROVED",
        "amount_cents": str(order.total_cents),
        "currency": order.currency,
    }
    form["checksum"] = processor.checksum(form["order_id"], transaction_id, "APPROVED")
    notification = processor.verify_notification(form)
    _, paid_now = service.record_payment(processor.name, notification)
    order.refresh_from_db()
    if paid_now:
        send_receipt(wiring.mailer, order, order.member)
    return {"status": order.status}
