import pytest

from sws_membership.members.member_numbers import (
    InvalidMemberNumber,
    allocate_member_number,
    normalise_member_number,
    reserve_member_numbers_through,
)


@pytest.mark.parametrize(
    ("scanned", "expected"),
    [
        ("123", 123),
        ("000123", 123),
        (" 0042 \n", 42),
        ("SWS-0042", 42),
        ("12 34", 1234),
    ],
)
def test_normalise_reduces_to_digits_without_leading_zeros(scanned, expected):
    assert normalise_member_number(scanned) == expected


@pytest.mark.parametrize("scanned", ["", "   ", "abc", "0", "000", "SWS-"])
def test_normalise_rejects_input_that_names_no_member(scanned):
    with pytest.raises(InvalidMemberNumber):
        normalise_member_number(scanned)


def test_allocation_hands_out_increasing_numbers(session):
    first = allocate_member_number(session)
    second = allocate_member_number(session)
    assert second == first + 1


# Sequences are not transactional, so these tests measure against where the
# sequence stands rather than assuming a fresh one.
def test_reserving_through_imported_numbers_moves_allocation_past_them(session):
    imported_highest = allocate_member_number(session) + 1000
    reserve_member_numbers_through(session, imported_highest)
    assert allocate_member_number(session) == imported_highest + 1


def test_reserving_never_moves_the_sequence_backwards(session):
    top = allocate_member_number(session) + 1000
    reserve_member_numbers_through(session, top)
    reserve_member_numbers_through(session, 10)
    assert allocate_member_number(session) == top + 1
