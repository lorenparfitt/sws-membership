"""Check-ins: one row per admission, naming the entitlement that admitted."""

import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sws_membership.database import Base


class Station(enum.Enum):
    """Where a check-in happens. Each station admits on its own entitlement kinds."""

    SPIT = "spit"
    SHUTTLE = "shuttle"


class CheckIn(Base):
    __tablename__ = "check_ins"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(
        ForeignKey("members.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entitlement_id: Mapped[int] = mapped_column(ForeignKey("entitlements.id"), nullable=False)
    station: Mapped[Station] = mapped_column(
        Enum(Station, name="station", values_callable=lambda s: [m.value for m in s]),
        nullable=False,
    )
    # The local calendar day, so one check-in per day is a plain unique rule.
    on_day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    checked_in_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    checked_in_by_member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), nullable=False)

    entitlement: Mapped["Entitlement"] = relationship()  # noqa: F821
