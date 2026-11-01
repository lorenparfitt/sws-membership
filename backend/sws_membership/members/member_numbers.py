"""Member numbers: one canonical form for scans, imports and new members.

A card barcode is Code128 of the member number. Scanners and imports deliver
it with padding, prefixes or stray characters, so every path reduces the
input to its digits and drops leading zeros before it touches the database.
The same function serves writes and lookups, which is what keeps them agreed.
"""

import re

from django.db import connection

MEMBER_NUMBER_SEQUENCE = "member_number_seq"

_NON_DIGITS = re.compile(r"\D")


class InvalidMemberNumber(ValueError):
    """The input holds no digits other than zeros, so it names no member."""


def normalise_member_number(scanned: str) -> int:
    digits = _NON_DIGITS.sub("", scanned)
    if not digits or int(digits) == 0:
        raise InvalidMemberNumber(scanned)
    return int(digits)


def allocate_member_number() -> int:
    """The next unused number for a new member."""
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT nextval('{MEMBER_NUMBER_SEQUENCE}')")
        return int(cursor.fetchone()[0])


def reserve_member_numbers_through(highest_existing: int) -> None:
    """Move the sequence past numbers that already exist, such as imported ones.

    Never moves it backwards, so calling it after a partial import is safe.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT setval('{MEMBER_NUMBER_SEQUENCE}', "
            f"GREATEST(%s, (SELECT last_value FROM {MEMBER_NUMBER_SEQUENCE})), true)",
            [highest_existing],
        )
