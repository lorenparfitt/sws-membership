"""Publishing waiver text, resetting signatures, signing, and judging currency.

A signature is current when it was made on the current template version and
after the latest reset. Publishing a new version therefore resets by
construction; the explicit reset exists for the admin who wants everyone to
re-sign the same text.
"""

import base64
import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sws_membership.members.models import Member
from sws_membership.storage.objects import ObjectStorage
from sws_membership.waivers.models import WaiverReset, WaiverSignature, WaiverTemplate

AGE_OF_MAJORITY = 18  # society rule: 17 and under need a guardian
PNG_PREFIX = "data:image/png;base64,"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
MAX_SIGNATURE_BYTES = 512 * 1024


def _now() -> datetime:
    return datetime.now(UTC)


def document_hash(body_text: str) -> str:
    return hashlib.sha256(body_text.encode("utf-8")).hexdigest()


def current_template(session: Session) -> WaiverTemplate | None:
    return session.scalars(
        select(WaiverTemplate).order_by(WaiverTemplate.version.desc()).limit(1)
    ).first()


def publish_template(
    session: Session, title: str, body_text: str, by: Member | None, now: datetime | None = None
) -> WaiverTemplate:
    latest = session.scalar(select(func.max(WaiverTemplate.version))) or 0
    template = WaiverTemplate(
        version=latest + 1,
        title=title.strip(),
        body_text=body_text,
        document_hash=document_hash(body_text),
        published_at=now or _now(),
        published_by_member_id=by.id if by else None,
    )
    session.add(template)
    session.flush()
    return template


def reset_signatures(
    session: Session, by: Member | None, reason: str, now: datetime | None = None
) -> WaiverReset:
    reset = WaiverReset(
        reset_at=now or _now(), reset_by_member_id=by.id if by else None, reason=reason.strip()
    )
    session.add(reset)
    session.flush()
    return reset


def latest_reset_at(session: Session) -> datetime | None:
    return session.scalar(select(func.max(WaiverReset.reset_at)))


def current_signature(session: Session, member: Member) -> WaiverSignature | None:
    """The member's signature that still counts, or None."""
    template = current_template(session)
    if template is None:
        return None
    reset_at = latest_reset_at(session)
    query = (
        select(WaiverSignature)
        .where(WaiverSignature.member_id == member.id, WaiverSignature.template_id == template.id)
        .order_by(WaiverSignature.signed_at.desc())
        .limit(1)
    )
    if reset_at is not None:
        query = query.where(WaiverSignature.signed_at > reset_at)
    return session.scalars(query).first()


def has_current_waiver(session: Session, member: Member) -> bool:
    return current_signature(session, member) is not None


def needs_guardian(member: Member, on: date) -> bool:
    born = member.date_of_birth
    if born is None:
        return True
    age = on.year - born.year - ((on.month, on.day) < (born.month, born.day))
    return age < AGE_OF_MAJORITY


class SignatureRejected(ValueError):
    pass


@dataclass(frozen=True)
class SignatureInput:
    signer_name: str
    signature_png: str  # data URL
    guardian_name: str | None = None
    guardian_signature_png: str | None = None


def _decode_png(data_url: str, what: str) -> bytes:
    if not data_url.startswith(PNG_PREFIX):
        raise SignatureRejected(f"{what} must be a PNG data URL")
    try:
        data = base64.b64decode(data_url[len(PNG_PREFIX) :], validate=True)
    except ValueError:
        raise SignatureRejected(f"{what} is not valid base64") from None
    if not data.startswith(PNG_MAGIC):
        raise SignatureRejected(f"{what} is not a PNG")
    if len(data) > MAX_SIGNATURE_BYTES:
        raise SignatureRejected(f"{what} is larger than {MAX_SIGNATURE_BYTES} bytes")
    return data


def sign(
    session: Session,
    storage: ObjectStorage,
    member: Member,
    template_id: int,
    given: SignatureInput,
    ip_address: str,
    now: datetime | None = None,
) -> WaiverSignature:
    now = now or _now()
    template = current_template(session)
    if template is None or template.id != template_id:
        raise SignatureRejected("that is not the current waiver; reload and sign again")
    if not given.signer_name.strip():
        raise SignatureRejected("type your full name")
    signature = _decode_png(given.signature_png, "signature")
    guardian_signature: bytes | None = None
    if needs_guardian(member, now.date()):
        if not (given.guardian_name or "").strip() or not given.guardian_signature_png:
            raise SignatureRejected("a parent or guardian must also sign for members under 18")
        guardian_signature = _decode_png(given.guardian_signature_png, "guardian signature")

    stamp = now.strftime("%Y%m%dT%H%M%S")
    key = f"waivers/{member.id}/{template.version}-{stamp}.png"
    storage.put(key, signature, "image/png")
    guardian_key = None
    if guardian_signature is not None:
        guardian_key = f"waivers/{member.id}/{template.version}-{stamp}-guardian.png"
        storage.put(guardian_key, guardian_signature, "image/png")

    row = WaiverSignature(
        member_id=member.id,
        template_id=template.id,
        signed_at=now,
        ip_address=ip_address,
        signer_name=given.signer_name.strip(),
        signature_key=key,
        document_hash=template.document_hash,
        guardian_name=(given.guardian_name or "").strip() or None,
        guardian_signature_key=guardian_key,
    )
    session.add(row)
    session.flush()
    return row
