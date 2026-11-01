"""Passwords beside the emailed link.

A member may set a password once signed in by any means. Signing in with it
opens the same kind of session as a redeemed link. A forgotten password is
not a separate flow: the emailed link signs the member in, and they set a
new one. Hashes are argon2id through Django's hasher, which also runs the
hash on unknown addresses so every failure takes the same time.
"""

from django.contrib.auth import authenticate as django_authenticate

from sws_membership.members.models import Member

MINIMUM_LENGTH = 10


class WeakPassword(ValueError):
    pass


def set_password(member: Member, password: str) -> None:
    if len(password) < MINIMUM_LENGTH:
        raise WeakPassword(f"at least {MINIMUM_LENGTH} characters")
    member.set_password(password)
    member.save(update_fields=["password", "updated_at"])


def authenticate(request, email: str, password: str) -> Member | None:
    """The member if the password matches; None for any other reason, alike."""
    return django_authenticate(request, username=email, password=password)
