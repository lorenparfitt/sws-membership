"""Finding a member at the gate and admitting them.

A station admits on a closed list of entitlement kinds, in order of
preference: a season pass is used before a day visit is spent. One
admission per member per station per day; a second scan the same day
reports the first and spends nothing. A pass whose product carries the
waiver rule admits only while the member's waiver signature is current.
"""

from dataclasses import dataclass
from datetime import date

from django.db.models import Count, Q, Value
from django.db.models.functions import Concat

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


def search_members(query: str) -> list[Member]:
    """A scan or typed number first, then an email, then a name fragment."""
    query = query.strip()
    if not query:
        return []
    try:
        normalise_member_number(query)
    except InvalidMemberNumber:
        pass
    else:
        member = find_member_by_scan(query)
        return [member] if member else []
    if "@" in query:
        member = find_member_by_email(query)
        return [member] if member else []
    return list(
        Member.objects.annotate(full_name=Concat("first_name", Value(" "), "last_name"))
        .filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(full_name__icontains=query)
        )
        .order_by("last_name", "first_name")[:MAX_SEARCH_RESULTS]
    )


@dataclass(frozen=True)
class GateView:
    member: Member
    entitlements: list[Entitlement]
    waiver_current: bool
    today_check_ins: list[CheckIn]


def gate_view(member: Member, today: date) -> GateView:
    entitlements = list(
        member.entitlements.held()
        .select_related("product")
        .prefetch_related("product__rules")
        .order_by("-valid_to", "id")
    )
    today_check_ins = list(
        member.check_ins.filter(on_day=today).select_related("entitlement__product")
    )
    return GateView(member, entitlements, has_current_waiver(member), today_check_ins)


class CheckInRefused(Exception):
    pass


def _needs_waiver(entitlement: Entitlement) -> bool:
    return any(
        rule.kind == RuleKind.REQUIRES_CURRENT_WAIVER for rule in entitlement.product.rules.all()
    )


def check_in(member: Member, staff: Member, station: Station, today: date) -> tuple[CheckIn, bool]:
    """Admit the member; return the check-in and whether it is new today."""
    existing = (
        member.check_ins.filter(station=station, on_day=today)
        .select_related("entitlement__product")
        .first()
    )
    if existing is not None:
        return existing, False

    view = gate_view(member, today)
    candidates = [
        e
        for kind in ADMITS[station]
        for e in view.entitlements
        if e.kind == kind and e.is_active_on(today)
    ]
    if not candidates:
        raise CheckInRefused(f"no valid pass for the {station.value} today")
    admitting = candidates[0]
    if _needs_waiver(admitting) and not view.waiver_current:
        raise CheckInRefused("waiver not signed for the current version")

    if admitting.kind in (EntitlementKind.DAY_VISITS, EntitlementKind.SHUTTLE_ACCESS):
        admitting.visits_remaining = (admitting.visits_remaining or 0) - 1
        admitting.save(update_fields=["visits_remaining"])
    row = CheckIn.objects.create(
        member=member, entitlement=admitting, station=station, on_day=today, checked_in_by=staff
    )
    return row, True


def counts_for(today: date) -> dict[str, int]:
    counts = {station.value: 0 for station in Station}
    for row in CheckIn.objects.filter(on_day=today).values("station").annotate(n=Count("id")):
        counts[row["station"]] = row["n"]
    return counts
