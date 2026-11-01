"""Gathering the facts about a member that eligibility is judged on."""

from sws_membership.catalog.eligibility import Held, MemberFacts
from sws_membership.members.models import Member
from sws_membership.waivers.service import has_current_waiver


def facts_for(member: Member) -> MemberFacts:
    rows = member.entitlements.held().select_related("product")
    return MemberFacts(
        date_of_birth=member.date_of_birth,
        entitlements=tuple(Held.of_row(row) for row in rows),
        has_current_waiver=has_current_waiver(member),
        profile_complete=member.profile_complete,
    )
