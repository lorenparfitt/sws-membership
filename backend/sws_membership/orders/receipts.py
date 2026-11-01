"""The receipt a member gets when an order is paid."""

from django.utils import timezone

from sws_membership.mail.mailer import EmailMessage, Mailer
from sws_membership.members.models import Member
from sws_membership.orders.models import Order


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


def send_receipt(mailer: Mailer, order: Order, member: Member) -> None:
    mailer.send(
        EmailMessage(
            to=member.email,
            subject=f"Squamish Windsports receipt, order {order.id}",
            text=receipt_text(order, member),
        )
    )
