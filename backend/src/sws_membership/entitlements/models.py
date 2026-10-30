"""Entitlements: typed rights with a validity window, one row per grant."""

import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sws_membership.database import Base


class EntitlementKind(enum.Enum):
    """The closed list of rights a product can confer."""

    MEMBERSHIP = "membership"
    SEASON_ACCESS = "season_access"
    DAY_VISITS = "day_visits"
    SHUTTLE_ACCESS = "shuttle_access"


def entitlement_kind_column() -> Enum:
    return Enum(
        EntitlementKind,
        name="entitlement_kind",
        values_callable=lambda kinds: [kind.value for kind in kinds],
    )


class Entitlement(Base):
    __tablename__ = "entitlements"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(
        ForeignKey("members.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[EntitlementKind] = mapped_column(entitlement_kind_column(), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date] = mapped_column(Date, nullable=False)
    # Only for DAY_VISITS: how many visits are left to consume.
    visits_remaining: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    product: Mapped["Product"] = relationship()  # noqa: F821

    def is_active_on(self, day: date) -> bool:
        if not (self.valid_from <= day <= self.valid_to):
            return False
        if self.kind is EntitlementKind.DAY_VISITS:
            return (self.visits_remaining or 0) > 0
        return True
