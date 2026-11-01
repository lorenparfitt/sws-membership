"""Sign-in by emailed link: request one, redeem it."""

from datetime import datetime, timedelta

from django.utils import timezone

from sws_membership.accounts.models import LoginToken
from sws_membership.accounts.tokens import hash_token, new_token
from sws_membership.mail.mailer import EmailMessage, Mailer
from sws_membership.members.lookup import find_member_by_email
from sws_membership.members.models import Member

LOGIN_LINK_LIFETIME = timedelta(minutes=15)


def request_login_link(
    mailer: Mailer, email: str, frontend_base_url: str, now: datetime | None = None
) -> None:
    """Email a sign-in link if the address belongs to a member.

    Silent for unknown addresses so the endpoint does not reveal who is a
    member.
    """
    now = now or timezone.now()
    member = find_member_by_email(email)
    if member is None:
        return
    token = new_token()
    LoginToken.objects.create(
        token_hash=hash_token(token),
        member=member,
        created_at=now,
        expires_at=now + LOGIN_LINK_LIFETIME,
    )
    link = f"{frontend_base_url.rstrip('/')}/sign-in?token={token}"
    minutes = int(LOGIN_LINK_LIFETIME.total_seconds() // 60)
    mailer.send(
        EmailMessage(
            to=member.email,
            subject="Your Squamish Windsports sign-in link",
            text=(
                f"Hello {member.first_name},\n\n"
                f"Sign in here: {link}\n\n"
                f"The link works once and expires in {minutes} minutes. "
                "If you did not ask for it, ignore this email."
            ),
        )
    )


class LoginLinkRejected(Exception):
    """The presented login token is unknown, used, or expired."""


def redeem_login_link(token: str, now: datetime | None = None) -> Member:
    now = now or timezone.now()
    login = LoginToken.objects.select_related("member").filter(token_hash=hash_token(token)).first()
    if login is None or login.used_at is not None or login.expires_at <= now:
        raise LoginLinkRejected()
    login.used_at = now
    login.save(update_fields=["used_at"])
    return login.member
