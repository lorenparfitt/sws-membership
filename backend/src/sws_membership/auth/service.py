"""Sign-in flow: request a link, redeem it, keep and end a session."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from sws_membership.auth.models import LoginToken, MemberSession
from sws_membership.auth.tokens import hash_token, new_token
from sws_membership.mail.mailer import EmailMessage, Mailer
from sws_membership.members.lookup import find_member_by_email
from sws_membership.members.models import Member

LOGIN_LINK_LIFETIME = timedelta(minutes=15)
SESSION_LIFETIME = timedelta(days=30)


def _now() -> datetime:
    return datetime.now(UTC)


def request_login_link(
    session: Session,
    mailer: Mailer,
    email: str,
    frontend_base_url: str,
    now: datetime | None = None,
) -> None:
    """Email a sign-in link if the address belongs to a member.

    Silent for unknown addresses so the endpoint does not reveal who is a
    member.
    """
    now = now or _now()
    member = find_member_by_email(session, email)
    if member is None:
        return
    token = new_token()
    session.add(
        LoginToken(
            token_hash=hash_token(token),
            member_id=member.id,
            created_at=now,
            expires_at=now + LOGIN_LINK_LIFETIME,
        )
    )
    session.flush()
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


def redeem_login_link(session: Session, token: str, now: datetime | None = None) -> Member:
    now = now or _now()
    login = session.scalars(
        select(LoginToken).where(LoginToken.token_hash == hash_token(token))
    ).first()
    if login is None or login.used_at is not None or login.expires_at <= now:
        raise LoginLinkRejected()
    login.used_at = now
    session.flush()
    return login.member


def open_session(session: Session, member: Member, now: datetime | None = None) -> str:
    """Start a session for the member and return the token the browser keeps."""
    now = now or _now()
    token = new_token()
    session.add(
        MemberSession(
            token_hash=hash_token(token),
            member_id=member.id,
            created_at=now,
            expires_at=now + SESSION_LIFETIME,
            last_seen_at=now,
        )
    )
    session.flush()
    return token


def resolve_session(session: Session, token: str, now: datetime | None = None) -> Member | None:
    now = now or _now()
    current = session.scalars(
        select(MemberSession).where(MemberSession.token_hash == hash_token(token))
    ).first()
    if current is None or current.expires_at <= now:
        return None
    current.last_seen_at = now
    return current.member


def close_session(session: Session, token: str) -> None:
    current = session.scalars(
        select(MemberSession).where(MemberSession.token_hash == hash_token(token))
    ).first()
    if current is not None:
        session.delete(current)
        session.flush()
