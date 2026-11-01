"""Staff view of one member: everything the kiosk needs to help them at the counter."""

from datetime import date, datetime

from ninja import Router, Schema
from ninja.errors import HttpError
from pydantic import EmailStr

from sws_membership import clock
from sws_membership.accounts.auth import admin_auth, staff_auth
from sws_membership.catalog.api import ProductView, catalog_for
from sws_membership.kiosk import service as kiosk
from sws_membership.kiosk.api import CheckInView, PassView, check_ins_of, passes_of
from sws_membership.members import profile
from sws_membership.members.api import ProfileView, load_member
from sws_membership.members.lookup import find_member_by_email
from sws_membership.members.models import Member, MemberRole, Sport, normalise_email
from sws_membership.members.roles import grant_role, revoke_role
from sws_membership.orders.api import ORDER_PREFETCH, OrderView
from sws_membership.waivers.service import current_signature

router = Router(tags=["staff-members"])


class MemberDetail(Schema):
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


class StaffProfileBody(Schema):
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


class RolesBody(Schema):
    roles: list[MemberRole]


def detail(member: Member, today: date) -> MemberDetail:
    gate = kiosk.gate_view(member, today)
    signature = current_signature(member)
    orders = member.orders.prefetch_related(*ORDER_PREFETCH)[:50]
    return MemberDetail(
        id=member.id,
        member_number=member.member_number,
        roles=member.role_values(),
        has_photo=member.photo_key is not None,
        profile=ProfileView.of(member),
        waiver_current=signature is not None,
        waiver_signed_at=signature.signed_at if signature else None,
        passes=passes_of(gate, today),
        today=check_ins_of(gate),
        orders=[OrderView.of(o) for o in orders],
        catalog=catalog_for(member, today),
    )


@router.get("/{member_id}", auth=staff_auth, response=MemberDetail)
def member_detail(request, member_id: int):
    return detail(load_member(member_id), clock.today())


@router.put("/{member_id}/profile", auth=staff_auth, response=MemberDetail)
def staff_update_profile(request, member_id: int, body: StaffProfileBody):
    """Staff may correct anything, including the birth date and email."""
    today = clock.today()
    member = load_member(member_id)
    email = normalise_email(body.email)
    other = find_member_by_email(email)
    if other is not None and other.id != member.id:
        raise HttpError(409, "another member has that email")
    if body.date_of_birth is not None and body.date_of_birth > today:
        raise HttpError(400, "date of birth is in the future")
    member.email = email
    member.date_of_birth = body.date_of_birth
    try:
        profile.update_profile(
            member,
            profile.ProfileInput(
                **body.dict(exclude={"sports", "email"}), sports=tuple(body.sports)
            ),
        )
    except profile.ProfileRejected as why:
        raise HttpError(400, str(why))
    return detail(member, today)


@router.put("/{member_id}/roles", auth=admin_auth, response=MemberDetail)
def set_roles(request, member_id: int, body: RolesBody):
    member = load_member(member_id)
    wanted = set(body.roles)
    for role in MemberRole:
        if role in wanted:
            grant_role(member.email, role)
        else:
            revoke_role(member.email, role)
    return detail(member, clock.today())
