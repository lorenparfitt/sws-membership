"""One row per card printed, so staff can see who still needs one."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from sws_membership.database import Base


class CardPrint(Base):
    __tablename__ = "card_prints"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(
        ForeignKey("members.id", ondelete="CASCADE"), nullable=False, index=True
    )
    printed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    printed_by_member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), nullable=False)
