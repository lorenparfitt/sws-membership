"""The receipt a member gets when an order is paid."""

from django.utils import timezone

from sws_membership.mail.mailer import EmailMessage, Mailer
from sws_membership.members.models import Member
from sws_membership.orders.models import Order, PaymentMethod, Refund


def receipt_text(order: Order, member: Member) -> str:
    lines = "\n".join(
        f"  {line.product_name:<40} ${line.amount_cents / 100:>9.2f}" for line in order.lines.all()
    )
    paid = timezone.localtime(order.paid_at).strftime("%Y-%m-%d %H:%M %Z") if order.paid_at else ""
    return (
        f"Hello {member.first_name},\n\n"
        f"Thank you. Your order {order.id} is paid.\n\n"
        f"{lines}\n"
        f"  {'Total':<40} ${order.total_cents / 100:>9.2f} {order.currency}\n\n"
        f"Paid by {order.payment_method} on {paid}.\n"
        f"Member number {member.member_number}. Your passes are on your account now.\n\n"
        "Squamish Windsports Society\n"
    )


def refund_notice_text(refund: Refund, member: Member) -> str:
    order = refund.order
    items = ", ".join(line.product_name for line in order.lines.all())
    how = (
        "to the card that paid for it; allow a few days for it to show on the statement"
        if order.payment_method == PaymentMethod.CARD
        else f"in {order.payment_method} at the counter"
    )
    return (
        f"Hello {member.first_name},\n\n"
        f"Your order {order.id} ({items}) has been refunded.\n\n"
        f"  {'Refunded':<40} ${refund.amount_cents / 100:>9.2f} {order.currency}\n\n"
        f"The refund goes {how}.\n"
        "The passes this order bought are no longer valid.\n\n"
        "Squamish Windsports Society\n"
    )


def send_refund_notice(mailer: Mailer, refund: Refund, member: Member) -> None:
    mailer.send(
        EmailMessage(
            to=member.email,
            subject=f"Squamish Windsports refund, order {refund.order_id}",
            text=refund_notice_text(refund, member),
        )
    )


def send_receipt(mailer: Mailer, order: Order, member: Member) -> None:
    mailer.send(
        EmailMessage(
            to=member.email,
            subject=f"Squamish Windsports receipt, order {order.id}",
            text=receipt_text(order, member),
        )
    )
