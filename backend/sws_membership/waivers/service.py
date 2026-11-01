"""Publishing waiver text, resetting signatures, signing, and judging currency.

A signature is current when it was made on the current template version and
after the latest reset. Publishing a new version therefore resets by
construction; the explicit reset exists for the admin who wants everyone to
re-sign the same text.
"""

import base64
import hashlib
from dataclasses import dataclass
from datetime import date, datetime

from django.db.models import Max
from django.utils import timezone

from sws_membership.members.models import Member
from sws_membership.storage.objects import ObjectStorage
from sws_membership.waivers.models import WaiverReset, WaiverSignature, WaiverTemplate

AGE_OF_MAJORITY = 18  # society rule: 17 and under need a guardian
PNG_PREFIX = "data:image/png;base64,"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
MAX_SIGNATURE_BYTES = 512 * 1024


def document_hash(body_text: str) -> str:
    return hashlib.sha256(body_text.encode("utf-8")).hexdigest()


def current_template() -> WaiverTemplate | None:
    return WaiverTemplate.objects.order_by("-version").first()


def publish_template(
    title: str, body_text: str, by: Member | None, now: datetime | None = None
) -> WaiverTemplate:
    latest = WaiverTemplate.objects.aggregate(top=Max("version"))["top"] or 0
    return WaiverTemplate.objects.create(
        version=latest + 1,
        title=title.strip(),
        body_text=body_text,
        document_hash=document_hash(body_text),
        published_at=now or timezone.now(),
        published_by=by,
    )


def reset_signatures(by: Member | None, reason: str, now: datetime | None = None) -> WaiverReset:
    return WaiverReset.objects.create(
        reset_at=now or timezone.now(), reset_by=by, reason=reason.strip()
    )


def latest_reset_at() -> datetime | None:
    return WaiverReset.objects.aggregate(top=Max("reset_at"))["top"]


def current_signature(member: Member) -> WaiverSignature | None:
    """The member's signature that still counts, or None."""
    template = current_template()
    if template is None:
        return None
    query = WaiverSignature.objects.filter(member=member, template=template)
    reset_at = latest_reset_at()
    if reset_at is not None:
        query = query.filter(signed_at__gt=reset_at)
    return query.order_by("-signed_at").first()


def has_current_waiver(member: Member) -> bool:
    return current_signature(member) is not None


def needs_guardian(date_of_birth: date | None, on: date) -> bool:
    if date_of_birth is None:
        return True
    born = date_of_birth
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
    storage: ObjectStorage,
    member: Member,
    template_id: int,
    given: SignatureInput,
    ip_address: str,
    now: datetime | None = None,
) -> WaiverSignature:
    now = now or timezone.now()
    template = current_template()
    if template is None or template.id != template_id:
        raise SignatureRejected("that is not the current waiver; reload and sign again")
    if not given.signer_name.strip():
        raise SignatureRejected("type your full name")
    signature = _decode_png(given.signature_png, "signature")
    guardian_signature: bytes | None = None
    if needs_guardian(member.date_of_birth, now.date()):
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

    return WaiverSignature.objects.create(
        member=member,
        template=template,
        signed_at=now,
        ip_address=ip_address,
        signer_name=given.signer_name.strip(),
        signature_key=key,
        document_hash=template.document_hash,
        guardian_name=(given.guardian_name or "").strip() or None,
        guardian_signature_key=guardian_key,
    )
