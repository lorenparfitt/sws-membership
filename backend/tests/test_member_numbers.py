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


def test_reserving_through_imported_numbers_moves_allocation_past_them(session):
    reserve_member_numbers_through(session, 500_000)
    assert allocate_member_number(session) == 500_001


def test_reserving_never_moves_the_sequence_backwards(session):
    reserve_member_numbers_through(session, 900_000)
    reserve_member_numbers_through(session, 10)
    assert allocate_member_number(session) == 900_001
