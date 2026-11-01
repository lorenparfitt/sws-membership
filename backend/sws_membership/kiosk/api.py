"""Staff-only kiosk routes."""

from datetime import date, datetime

from ninja import Router, Schema
from ninja.errors import HttpError

from sws_membership import clock
from sws_membership.accounts.auth import staff_auth
from sws_membership.kiosk import service
from sws_membership.kiosk.models import Station
from sws_membership.members.api import load_member

router = Router(tags=["kiosk"])


class PassView(Schema):
    id: int
    kind: str
    product_name: str
    valid_from: date
    valid_to: date
    visits_remaining: int | None
    active: bool


class CheckInView(Schema):
    station: str
    checked_in_at: datetime
    product_name: str


class MemberGateView(Schema):
    id: int
    member_number: int
    first_name: str
    last_name: str
    email: str
    date_of_birth: date | None
    photo_key: str | None
    waiver_current: bool
    passes: list[PassView]
    today: list[CheckInView]


class CheckInBody(Schema):
    member_id: int
    station: Station


class CheckInResult(Schema):
    admitted: bool
    new_today: bool
    message: str
    member: MemberGateView


def passes_of(view: service.GateView, today: date) -> list[PassView]:
    return [
        PassView(
            id=e.id,
            kind=e.kind,
            product_name=e.product.name,
            valid_from=e.valid_from,
            valid_to=e.valid_to,
            visits_remaining=e.visits_remaining,
            active=e.is_active_on(today),
        )
        for e in view.entitlements
    ]


def check_ins_of(view: service.GateView) -> list[CheckInView]:
    return [
        CheckInView(
            station=c.station,
            checked_in_at=c.checked_in_at,
            product_name=c.entitlement.product.name,
        )
        for c in view.today_check_ins
    ]


def member_view(view: service.GateView, today: date) -> MemberGateView:
    m = view.member
    return MemberGateView(
        id=m.id,
        member_number=m.member_number,
        first_name=m.first_name,
        last_name=m.last_name,
        email=m.email,
        date_of_birth=m.date_of_birth,
        photo_key=m.photo_key,
        waiver_current=view.waiver_current,
        passes=passes_of(view, today),
        today=check_ins_of(view),
    )


@router.get("/lookup", auth=staff_auth, response=list[MemberGateView])
def lookup(request, q: str):
    """Find members by scanned number, email or name, with passes and waiver status."""
    today = clock.today()
    return [member_view(service.gate_view(m, today), today) for m in service.search_members(q)]


@router.post("/check-in", auth=staff_auth, response=CheckInResult)
def check_in(request, body: CheckInBody):
    """Admit a member at a station on their best pass; one admission per station per day."""
    today = clock.today()
    member = load_member(body.member_id)
    try:
        row, new_today = service.check_in(member, request.auth, body.station, today)
    except service.CheckInRefused as why:
        view = service.gate_view(member, today)
        return CheckInResult(
            admitted=False, new_today=False, message=str(why), member=member_view(view, today)
        )
    view = service.gate_view(member, today)
    message = (
        f"checked in on {row.entitlement.product.name}"
        if new_today
        else f"already checked in today on {row.entitlement.product.name}"
    )
    return CheckInResult(
        admitted=True, new_today=new_today, message=message, member=member_view(view, today)
    )


@router.get("/today", auth=staff_auth)
def today_counts(request) -> dict[str, int]:
    """Check-ins so far today, per station."""
    return service.counts_for(clock.today())


__all__ = ["HttpError", "router"]
