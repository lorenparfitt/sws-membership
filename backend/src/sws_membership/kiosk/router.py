"""Staff-only kiosk routes."""

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from sws_membership.auth.dependencies import DatabaseSession, require_role
from sws_membership.catalog.router import CurrentDay
from sws_membership.kiosk import service
from sws_membership.kiosk.models import Station
from sws_membership.members.models import Member, MemberRole

router = APIRouter(prefix="/api/staff/kiosk", tags=["kiosk"])

Staff = Annotated[Member, Depends(require_role(MemberRole.STAFF))]


class PassView(BaseModel):
    id: int
    kind: str
    product_name: str
    valid_from: date
    valid_to: date
    visits_remaining: int | None
    active: bool


class CheckInView(BaseModel):
    station: str
    checked_in_at: datetime
    product_name: str


class MemberGateView(BaseModel):
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


class CheckInBody(BaseModel):
    member_id: int
    station: Station


class CheckInResult(BaseModel):
    admitted: bool
    new_today: bool
    message: str
    member: MemberGateView


def _member_view(view: service.GateView, today: date) -> MemberGateView:
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
        passes=[
            PassView(
                id=e.id,
                kind=e.kind.value,
                product_name=e.product.name,
                valid_from=e.valid_from,
                valid_to=e.valid_to,
                visits_remaining=e.visits_remaining,
                active=e.is_active_on(today),
            )
            for e in view.entitlements
        ],
        today=[
            CheckInView(
                station=c.station.value,
                checked_in_at=c.checked_in_at,
                product_name=c.entitlement.product.name,
            )
            for c in view.today_check_ins
        ],
    )


@router.get("/lookup")
def lookup(
    q: str, session: DatabaseSession, today: CurrentDay, staff: Staff
) -> list[MemberGateView]:
    return [
        _member_view(service.gate_view(session, m, today), today)
        for m in service.search_members(session, q)
    ]


@router.post("/check-in")
def check_in(
    body: CheckInBody, session: DatabaseSession, today: CurrentDay, staff: Staff
) -> CheckInResult:
    member = session.get(Member, body.member_id)
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such member")
    try:
        row, new_today = service.check_in(session, member, staff, body.station, today)
    except service.CheckInRefused as why:
        view = service.gate_view(session, member, today)
        return CheckInResult(
            admitted=False, new_today=False, message=str(why), member=_member_view(view, today)
        )
    view = service.gate_view(session, member, today)
    message = (
        f"checked in on {row.entitlement.product.name}"
        if new_today
        else f"already checked in today on {row.entitlement.product.name}"
    )
    return CheckInResult(
        admitted=True, new_today=new_today, message=message, member=_member_view(view, today)
    )


@router.get("/today")
def today_counts(session: DatabaseSession, today: CurrentDay, staff: Staff) -> dict[str, int]:
    return service.counts_for(session, today)
