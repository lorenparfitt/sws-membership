"""Gathering the facts about a member that eligibility is judged on."""

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from sws_membership.catalog.eligibility import MemberFacts
from sws_membership.entitlements.models import Entitlement
from sws_membership.members.models import Member


def facts_for(session: Session, member: Member) -> MemberFacts:
    entitlements = session.scalars(
        select(Entitlement)
        .where(Entitlement.member_id == member.id)
        .options(selectinload(Entitlement.product))
    ).all()
    return MemberFacts(date_of_birth=member.date_of_birth, entitlements=tuple(entitlements))
