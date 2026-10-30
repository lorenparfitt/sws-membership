"""Member numbers: one canonical form for scans, imports and new members.

A card barcode is Code128 of the member number. Scanners and imports deliver
it with padding, prefixes or stray characters, so every path reduces the
input to its digits and drops leading zeros before it touches the database.
The same function serves writes and lookups, which is what keeps them agreed.
"""

import re

from sqlalchemy import Sequence, select, text
from sqlalchemy.orm import Session

from sws_membership.database import Base

MEMBER_NUMBER_SEQUENCE = Sequence("member_number_seq", metadata=Base.metadata)

_NON_DIGITS = re.compile(r"\D")


class InvalidMemberNumber(ValueError):
    """The input holds no digits other than zeros, so it names no member."""


def normalise_member_number(scanned: str) -> int:
    digits = _NON_DIGITS.sub("", scanned)
    if not digits or int(digits) == 0:
        raise InvalidMemberNumber(scanned)
    return int(digits)


def allocate_member_number(session: Session) -> int:
    """The next unused number for a new member."""
    return session.scalar(select(MEMBER_NUMBER_SEQUENCE.next_value()))


def reserve_member_numbers_through(session: Session, highest_existing: int) -> None:
    """Move the sequence past numbers that already exist, such as imported ones.

    Never moves it backwards, so calling it after a partial import is safe.
    """
    sequence = MEMBER_NUMBER_SEQUENCE.name
    session.execute(
        text(
            f"SELECT setval('{sequence}', "
            f"GREATEST(:highest, (SELECT last_value FROM {sequence})), true)"
        ),
        {"highest": highest_existing},
    )
