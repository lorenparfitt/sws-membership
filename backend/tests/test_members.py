from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from sws_membership.members.lookup import find_member_by_email, find_member_by_scan
from sws_membership.members.member_numbers import allocate_member_number
from sws_membership.members.models import Member, MemberRole, MemberRoleAssignment


def _member(session, email="rider@example.com", member_number=None) -> Member:
    member = Member(
        member_number=(
            member_number if member_number is not None else allocate_member_number(session)
        ),
        first_name="Sam",
        last_name="Rider",
        email=email,
        date_of_birth=date(1990, 5, 1),
    )
    session.add(member)
    session.flush()
    return member


def test_scan_with_padding_finds_the_member(session):
    member = _member(session, member_number=4242)
    assert find_member_by_scan(session, "00004242") is member
    assert find_member_by_scan(session, "SWS-4242") is member


def test_scan_of_unknown_or_invalid_number_finds_nobody(session):
    _member(session, member_number=4242)
    assert find_member_by_scan(session, "999999") is None
    assert find_member_by_scan(session, "no digits") is None


def test_email_lookup_ignores_case_and_whitespace(session):
    member = _member(session, email="rider@example.com")
    assert find_member_by_email(session, "  Rider@Example.com ") is member


def test_member_number_is_unique(session):
    _member(session, email="a@example.com", member_number=7)
    with pytest.raises(IntegrityError):
        _member(session, email="b@example.com", member_number=7)


def test_member_number_must_be_positive(session):
    with pytest.raises(IntegrityError):
        _member(session, member_number=0)


def test_roles_are_a_closed_list_held_per_member(session):
    member = _member(session)
    member.roles.append(MemberRoleAssignment(role=MemberRole.STAFF))
    session.flush()
    session.expire(member)
    assert member.has_role(MemberRole.STAFF)
    assert not member.has_role(MemberRole.ADMIN)
