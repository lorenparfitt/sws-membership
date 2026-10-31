"""Staff view of one member: everything the kiosk needs to help them at the counter."""

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from sws_membership.auth.dependencies import DatabaseSession, require_role
from sws_membership.catalog.router import CurrentDay, ProductView, catalog_for
from sws_membership.kiosk import service as kiosk
from sws_membership.members import profile
from sws_membership.members.lookup import find_member_by_email
from sws_membership.members.models import Member, MemberRole, Sport
from sws_membership.members.roles import grant_role, revoke_role
from sws_membership.members.router import ProfileView
from sws_membership.orders.models import Order
from sws_membership.waivers.service import current_signature

router = APIRouter(prefix="/api/staff/members", tags=["staff-members"])

Staff = Annotated[Member, Depends(require_role(MemberRole.STAFF))]
Admin = Annotated[Member, Depends(require_role(MemberRole.ADMIN))]


class PassView(BaseModel):
    id: int
    kind: str
    product_name: str
    valid_from: date
    valid_to: date
    visits_remaining: int | None
    active: bool


class OrderLineView(BaseModel):
    product_name: str
    amount_cents: int


class OrderView(BaseModel):
    id: int
    status: str
    payment_method: str
    total_cents: int
    created_at: datetime
    paid_at: datetime | None
    lines: list[OrderLineView]


class CheckInView(BaseModel):
    station: str
    checked_in_at: datetime
    product_name: str


class MemberDetail(BaseModel):
    id: int
    member_number: int
    roles: list[str]
    has_photo: bool
    profile: ProfileView
    waiver_current: bool
    waiver_signed_at: datetime | None
    passes: list[PassView]
    today: list[CheckInView]
    orders: list[OrderView]
    catalog: list[ProductView]


class StaffProfileBody(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    phone: str | None = None
    date_of_birth: date | None = None
    address_line_1: str | None = None
    address_line_2: str | None = None
    city: str | None = None
    province: str | None = None
    postal_code: str | None = None
    sports: list[Sport] = []


class RolesBody(BaseModel):
    roles: list[MemberRole]


def _load(session, member_id: int) -> Member:
    member = session.get(Member, member_id)
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such member")
    return member


def _detail(session, member: Member, today: date) -> MemberDetail:
    gate = kiosk.gate_view(session, member, today)
    signature = current_signature(session, member)
    orders = session.scalars(
        select(Order)
        .where(Order.member_id == member.id)
        .options(selectinload(Order.lines))
        .order_by(Order.created_at.desc())
        .limit(50)
    ).all()
    return MemberDetail(
        id=member.id,
        member_number=member.member_number,
        roles=sorted(r.role.value for r in member.roles),
        has_photo=member.photo_key is not None,
        profile=ProfileView.of(member),
        waiver_current=signature is not None,
        waiver_signed_at=signature.signed_at if signature else None,
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
            for e in gate.entitlements
        ],
        today=[
            CheckInView(
                station=c.station.value,
                checked_in_at=c.checked_in_at,
                product_name=c.entitlement.product.name,
            )
            for c in gate.today_check_ins
        ],
        orders=[
            OrderView(
                id=o.id,
                status=o.status.value,
                payment_method=o.payment_method.value,
                total_cents=o.total_cents,
                created_at=o.created_at,
                paid_at=o.paid_at,
                lines=[
                    OrderLineView(product_name=l.product_name, amount_cents=l.amount_cents)
                    for l in o.lines
                ],
            )
            for o in orders
        ],
        catalog=catalog_for(session, member, today),
    )


@router.get("/{member_id}")
def member_detail(
    member_id: int, session: DatabaseSession, today: CurrentDay, staff: Staff
) -> MemberDetail:
    return _detail(session, _load(session, member_id), today)


@router.put("/{member_id}/profile")
def staff_update_profile(
    member_id: int,
    body: StaffProfileBody,
    session: DatabaseSession,
    today: CurrentDay,
    staff: Staff,
) -> MemberDetail:
    """Staff may correct anything, including the birth date and email."""
    member = _load(session, member_id)
    email = body.email.strip().lower()
    other = find_member_by_email(session, email)
    if other is not None and other.id != member.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "another member has that email")
    if body.date_of_birth is not None and body.date_of_birth > today:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "date of birth is in the future")
    member.email = email
    member.date_of_birth = body.date_of_birth
    try:
        profile.update_profile(
            session,
            member,
            profile.ProfileInput(
                **body.model_dump(exclude={"sports", "email"}), sports=tuple(body.sports)
            ),
        )
    except profile.ProfileRejected as why:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(why))
    return _detail(session, member, today)


@router.put("/{member_id}/roles")
def set_roles(
    member_id: int, body: RolesBody, session: DatabaseSession, today: CurrentDay, admin: Admin
) -> MemberDetail:
    member = _load(session, member_id)
    wanted = set(body.roles)
    for role in MemberRole:
        if role in wanted:
            grant_role(session, member.email, role)
        else:
            revoke_role(session, member.email, role)
    return _detail(session, member, today)
