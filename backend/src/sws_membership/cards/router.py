"""Card downloads: a member's own, and staff prints for anyone."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select

from sws_membership.auth.dependencies import (
    CurrentMember,
    DatabaseSession,
    StorageDependency,
    require_role,
)
from sws_membership.cards import service
from sws_membership.catalog.router import CurrentDay
from sws_membership.members.models import Member, MemberRole
from sws_membership.settings import settings

router = APIRouter(prefix="/api", tags=["cards"])

Staff = Annotated[Member, Depends(require_role(MemberRole.STAFF))]


def _pdf(data: bytes, filename: str) -> Response:
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"content-disposition": f'inline; filename="{filename}"'},
    )


@router.get("/me/card.pdf")
def my_card(
    session: DatabaseSession, member: CurrentMember, today: CurrentDay, storage: StorageDependency
) -> Response:
    data = service.render_for_members(session, storage, [member], today, settings.shuttle_url)
    return _pdf(data, f"sws-card-{member.member_number}.pdf")


class BatchBody(BaseModel):
    member_ids: list[int]


@router.post("/staff/cards/print")
def print_cards(
    body: BatchBody,
    session: DatabaseSession,
    today: CurrentDay,
    staff: Staff,
    storage: StorageDependency,
) -> Response:
    """A PDF for the given members, and a print record for each."""
    if not body.member_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no members selected")
    members = session.scalars(select(Member).where(Member.id.in_(body.member_ids))).all()
    missing = set(body.member_ids) - {m.id for m in members}
    if missing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no such members: {sorted(missing)}")
    ordered = sorted(members, key=lambda m: body.member_ids.index(m.id))
    data = service.render_for_members(session, storage, ordered, today, settings.shuttle_url)
    service.record_prints(session, ordered, staff)
    return _pdf(data, "sws-cards.pdf")
