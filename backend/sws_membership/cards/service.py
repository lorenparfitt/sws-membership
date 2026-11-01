"""Assemble card data from a member and record prints."""

from datetime import date

from sws_membership.cards.models import CardPrint
from sws_membership.cards.render import CardData, render_cards
from sws_membership.entitlements.models import EntitlementKind
from sws_membership.members.models import SPORT_LABELS, Member, Sport
from sws_membership.storage.objects import ObjectStorage


def _season_label(member: Member, today: date) -> str:
    memberships = member.entitlements.filter(kind=EntitlementKind.MEMBERSHIP).select_related(
        "product"
    )
    active = [e for e in memberships if e.is_active_on(today)]
    if active:
        years = sorted({e.product.season_year for e in active})
        return f"{', '.join(str(y) for y in years)} member"
    return "No current membership"


def card_for(storage: ObjectStorage, member: Member, today: date, shuttle_url: str) -> CardData:
    return CardData(
        member_number=member.member_number,
        first_name=member.first_name,
        last_name=member.last_name,
        season_label=_season_label(member, today),
        sports_label=", ".join(
            sorted(SPORT_LABELS[Sport(row.sport)] for row in member.sports.all())
        ),
        shuttle_url=shuttle_url,
        printed_on=today,
        photo_jpeg=storage.get(member.photo_key) if member.photo_key else None,
    )


def render_for_members(
    storage: ObjectStorage, members: list[Member], today: date, shuttle_url: str
) -> bytes:
    return render_cards([card_for(storage, m, today, shuttle_url) for m in members])


def record_prints(members: list[Member], printed_by: Member) -> None:
    CardPrint.objects.bulk_create(CardPrint(member=m, printed_by=printed_by) for m in members)
