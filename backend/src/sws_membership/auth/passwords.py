"""Passwords beside the emailed link.

A member may set a password once signed in by any means. Signing in with it
opens the same kind of session as a redeemed link. A forgotten password is
not a separate flow: the emailed link signs the member in, and they set a
new one. Hashes are argon2id; verification is constant-time and a hash made
with older parameters is upgraded on the next successful sign-in.
"""

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy.orm import Session

from sws_membership.members.lookup import find_member_by_email
from sws_membership.members.models import Member

MINIMUM_LENGTH = 10
_hasher = PasswordHasher()


class WeakPassword(ValueError):
    pass


def set_password(session: Session, member: Member, password: str) -> None:
    if len(password) < MINIMUM_LENGTH:
        raise WeakPassword(f"at least {MINIMUM_LENGTH} characters")
    member.password_hash = _hasher.hash(password)
    session.flush()


def authenticate(session: Session, email: str, password: str) -> Member | None:
    """The member if the password matches; None for any other reason, alike."""
    member = find_member_by_email(session, email)
    if member is None or member.password_hash is None:
        return None
    try:
        _hasher.verify(member.password_hash, password)
    except VerifyMismatchError:
        return None
    if _hasher.check_needs_rehash(member.password_hash):
        member.password_hash = _hasher.hash(password)
        session.flush()
    return member
