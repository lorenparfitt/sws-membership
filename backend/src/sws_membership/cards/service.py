"""Assemble card data from a member and record prints."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from sws_membership.cards.models import CardPrint
from sws_membership.cards.render import CardData, render_cards
from sws_membership.entitlements.models import Entitlement, EntitlementKind
from sws_membership.members.models import SPORT_LABELS, Member
from sws_membership.storage.objects import ObjectStorage


def _season_label(session: Session, member: Member, today: date) -> str:
    memberships = session.scalars(
        select(Entitlement)
        .where(Entitlement.member_id == member.id, Entitlement.kind == EntitlementKind.MEMBERSHIP)
        .options(selectinload(Entitlement.product))
    ).all()
    active = [e for e in memberships if e.is_active_on(today)]
    if active:
        years = sorted({e.product.season_year for e in active})
        return f"{', '.join(str(y) for y in years)} member"
    return "No current membership"


def card_for(
    session: Session, storage: ObjectStorage, member: Member, today: date, shuttle_url: str
) -> CardData:
    return CardData(
        member_number=member.member_number,
        first_name=member.first_name,
        last_name=member.last_name,
        season_label=_season_label(session, member, today),
        sports_label=", ".join(sorted(SPORT_LABELS[row.sport] for row in member.sports)),
        shuttle_url=shuttle_url,
        printed_on=today,
        photo_jpeg=storage.get(member.photo_key) if member.photo_key else None,
    )


def render_for_members(
    session: Session, storage: ObjectStorage, members: list[Member], today: date, shuttle_url: str
) -> bytes:
    return render_cards([card_for(session, storage, m, today, shuttle_url) for m in members])


def record_prints(session: Session, members: list[Member], printed_by: Member) -> None:
    for member in members:
        session.add(CardPrint(member_id=member.id, printed_by_member_id=printed_by.id))
    session.flush()
