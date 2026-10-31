"""Finding a member at the gate and admitting them.

A station admits on a closed list of entitlement kinds, in order of
preference: a season pass is used before a day visit is spent. One
admission per member per station per day; a second scan the same day
reports the first and spends nothing. A pass whose product carries the
waiver rule admits only while the member's waiver signature is current.
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from sws_membership.catalog.models import RuleKind
from sws_membership.entitlements.models import Entitlement, EntitlementKind
from sws_membership.kiosk.models import CheckIn, Station
from sws_membership.members.lookup import find_member_by_email, find_member_by_scan
from sws_membership.members.member_numbers import InvalidMemberNumber, normalise_member_number
from sws_membership.members.models import Member
from sws_membership.waivers.service import has_current_waiver

ADMITS: dict[Station, tuple[EntitlementKind, ...]] = {
    Station.SPIT: (EntitlementKind.SEASON_ACCESS, EntitlementKind.DAY_VISITS),
    Station.SHUTTLE: (EntitlementKind.SHUTTLE_ACCESS,),
}
MAX_SEARCH_RESULTS = 20


def search_members(session: Session, query: str) -> list[Member]:
    """A scan or typed number first, then an email, then a name fragment."""
    query = query.strip()
    if not query:
        return []
    try:
        normalise_member_number(query)
    except InvalidMemberNumber:
        pass
    else:
        member = find_member_by_scan(session, query)
        return [member] if member else []
    if "@" in query:
        member = find_member_by_email(session, query)
        return [member] if member else []
    pattern = f"%{query}%"
    return list(
        session.scalars(
            select(Member)
            .where(
                or_(
                    Member.first_name.ilike(pattern),
                    Member.last_name.ilike(pattern),
                    (Member.first_name + " " + Member.last_name).ilike(pattern),
                )
            )
            .order_by(Member.last_name, Member.first_name)
            .limit(MAX_SEARCH_RESULTS)
        )
    )


@dataclass(frozen=True)
class GateView:
    member: Member
    entitlements: list[Entitlement]
    waiver_current: bool
    today_check_ins: list[CheckIn]


def gate_view(session: Session, member: Member, today: date) -> GateView:
    entitlements = list(
        session.scalars(
            select(Entitlement)
            .where(Entitlement.member_id == member.id)
            .options(selectinload(Entitlement.product))
            .order_by(Entitlement.valid_to.desc(), Entitlement.id)
        )
    )
    today_check_ins = list(
        session.scalars(
            select(CheckIn).where(CheckIn.member_id == member.id, CheckIn.on_day == today)
        )
    )
    return GateView(member, entitlements, has_current_waiver(session, member), today_check_ins)


class CheckInRefused(Exception):
    pass


def _needs_waiver(entitlement: Entitlement) -> bool:
    return any(rule.kind is RuleKind.REQUIRES_CURRENT_WAIVER for rule in entitlement.product.rules)


def check_in(
    session: Session, member: Member, staff: Member, station: Station, today: date
) -> tuple[CheckIn, bool]:
    """Admit the member; return the check-in and whether it is new today."""
    existing = session.scalars(
        select(CheckIn).where(
            CheckIn.member_id == member.id, CheckIn.station == station, CheckIn.on_day == today
        )
    ).first()
    if existing is not None:
        return existing, False

    view = gate_view(session, member, today)
    candidates = [
        e
        for kind in ADMITS[station]
        for e in view.entitlements
        if e.kind is kind and e.is_active_on(today)
    ]
    if not candidates:
        raise CheckInRefused(f"no valid pass for the {station.value} today")
    admitting = candidates[0]
    if _needs_waiver(admitting) and not view.waiver_current:
        raise CheckInRefused("waiver not signed for the current version")

    if admitting.kind in (EntitlementKind.DAY_VISITS, EntitlementKind.SHUTTLE_ACCESS):
        admitting.visits_remaining = (admitting.visits_remaining or 0) - 1
    row = CheckIn(
        member_id=member.id,
        entitlement_id=admitting.id,
        station=station,
        on_day=today,
        checked_in_by_member_id=staff.id,
    )
    session.add(row)
    session.flush()
    return row, True


def counts_for(session: Session, today: date) -> dict[str, int]:
    rows = session.execute(
        select(CheckIn.station, func.count())
        .where(CheckIn.on_day == today)
        .group_by(CheckIn.station)
    ).all()
    counts = {station.value: 0 for station in Station}
    for station, count in rows:
        counts[station.value] = count
    return counts
