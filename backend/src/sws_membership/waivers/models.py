"""Waiver templates, resets and signatures. Nothing here is ever edited after insert."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sws_membership.database import Base


class WaiverTemplate(Base):
    __tablename__ = "waiver_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    # sha256 of body_text, stored so a signature can cite exactly what was agreed.
    document_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_by_member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"))


class WaiverReset(Base):
    """An admin decision that every signature before this moment is stale."""

    __tablename__ = "waiver_resets"

    id: Mapped[int] = mapped_column(primary_key=True)
    reset_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reset_by_member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"))
    reason: Mapped[str] = mapped_column(String(300), nullable=False)


class WaiverSignature(Base):
    __tablename__ = "waiver_signatures"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(
        ForeignKey("members.id", ondelete="CASCADE"), nullable=False, index=True
    )
    template_id: Mapped[int] = mapped_column(ForeignKey("waiver_templates.id"), nullable=False)
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    signer_name: Mapped[str] = mapped_column(String(200), nullable=False)
    signature_key: Mapped[str] = mapped_column(String(200), nullable=False)
    document_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    guardian_name: Mapped[str | None] = mapped_column(String(200))
    guardian_signature_key: Mapped[str | None] = mapped_column(String(200))

    template: Mapped[WaiverTemplate] = relationship()
