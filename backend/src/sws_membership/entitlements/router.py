"""What the signed-in member holds."""

from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from sws_membership.auth.dependencies import CurrentMember, DatabaseSession
from sws_membership.catalog.router import CurrentDay
from sws_membership.entitlements.models import Entitlement

router = APIRouter(prefix="/api/entitlements", tags=["entitlements"])


class EntitlementView(BaseModel):
    id: int
    kind: str
    product_name: str
    valid_from: date
    valid_to: date
    visits_remaining: int | None
    active: bool


@router.get("")
def my_entitlements(
    session: DatabaseSession, member: CurrentMember, today: CurrentDay
) -> list[EntitlementView]:
    rows = session.scalars(
        select(Entitlement)
        .where(Entitlement.member_id == member.id)
        .options(selectinload(Entitlement.product))
        .order_by(Entitlement.valid_to.desc(), Entitlement.id)
    ).all()
    return [
        EntitlementView(
            id=row.id,
            kind=row.kind.value,
            product_name=row.product.name,
            valid_from=row.valid_from,
            valid_to=row.valid_to,
            visits_remaining=row.visits_remaining,
            active=row.is_active_on(today),
        )
        for row in rows
    ]
