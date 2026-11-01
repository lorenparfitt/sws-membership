from datetime import date

import pytest
from django.db import IntegrityError, transaction

from sws_membership.members.lookup import find_member_by_email, find_member_by_scan
from sws_membership.members.models import MemberRole, MemberRoleAssignment
from tests.conftest import make_member

pytestmark = pytest.mark.django_db


def _member(email="rider@example.com", member_number=None):
    fields = {"date_of_birth": date(1990, 5, 1)}
    if member_number is not None:
        fields["member_number"] = member_number
    return make_member(email, **fields)


def test_scan_with_padding_finds_the_member():
    member = _member(member_number=4242)
    assert find_member_by_scan("00004242") == member
    assert find_member_by_scan("SWS-4242") == member


def test_scan_of_unknown_or_invalid_number_finds_nobody():
    _member(member_number=4242)
    assert find_member_by_scan("999999") is None
    assert find_member_by_scan("no digits") is None


def test_email_lookup_ignores_case_and_whitespace():
    member = _member(email="rider@example.com")
    assert find_member_by_email("  Rider@Example.com ") == member


def test_member_number_is_unique():
    _member(email="a@example.com", member_number=7)
    with pytest.raises(IntegrityError), transaction.atomic():
        _member(email="b@example.com", member_number=7)


def test_member_number_must_be_positive():
    with pytest.raises(IntegrityError), transaction.atomic():
        _member(member_number=0)


def test_roles_are_a_closed_list_held_per_member():
    member = _member()
    MemberRoleAssignment.objects.create(member=member, role=MemberRole.STAFF)
    assert member.has_role(MemberRole.STAFF)
    assert not member.has_role(MemberRole.ADMIN)
    assert member.is_staff is False  # Django admin is for the admin role only
