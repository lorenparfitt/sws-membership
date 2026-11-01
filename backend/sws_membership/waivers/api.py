"""Reading, signing, publishing and resetting the waiver."""

from datetime import datetime

from ninja import Router, Schema, Status
from ninja.errors import HttpError

from sws_membership import clock
from sws_membership.accounts.auth import admin_auth, member_auth
from sws_membership.members.models import Member
from sws_membership.waivers import service
from sws_membership.wiring import wiring

router = Router(tags=["waivers"])


class WaiverView(Schema):
    template_id: int | None
    version: int | None
    title: str | None
    body_text: str | None
    document_hash: str | None
    signed: bool
    signed_at: datetime | None
    needs_guardian: bool


class SignatureBody(Schema):
    template_id: int
    signer_name: str
    signature_png: str
    guardian_name: str | None = None
    guardian_signature_png: str | None = None


class PublishBody(Schema):
    title: str
    body_text: str


class ResetBody(Schema):
    reason: str


def waiver_view(member: Member) -> WaiverView:
    template = service.current_template()
    signature = service.current_signature(member) if template else None
    return WaiverView(
        template_id=template.id if template else None,
        version=template.version if template else None,
        title=template.title if template else None,
        body_text=template.body_text if template else None,
        document_hash=template.document_hash if template else None,
        signed=signature is not None,
        signed_at=signature.signed_at if signature else None,
        needs_guardian=service.needs_guardian(member.date_of_birth, clock.today()),
    )


def client_address(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return forwarded.split(",")[0].strip() or request.META.get("REMOTE_ADDR", "unknown")


@router.get("/waiver", auth=member_auth, response=WaiverView)
def waiver(request):
    return waiver_view(request.auth)


@router.post("/waiver/sign", auth=member_auth, response={201: WaiverView})
def sign(request, body: SignatureBody):
    try:
        service.sign(
            wiring.storage,
            request.auth,
            body.template_id,
            service.SignatureInput(
                signer_name=body.signer_name,
                signature_png=body.signature_png,
                guardian_name=body.guardian_name,
                guardian_signature_png=body.guardian_signature_png,
            ),
            ip_address=client_address(request),
        )
    except service.SignatureRejected as why:
        raise HttpError(400, str(why))
    return Status(201, waiver_view(request.auth))


@router.post("/admin/waiver/publish", auth=admin_auth, response={201: dict})
def publish(request, body: PublishBody):
    if not body.title.strip() or not body.body_text.strip():
        raise HttpError(400, "title and text are required")
    template = service.publish_template(body.title, body.body_text, by=request.auth)
    return Status(201, {"template_id": template.id, "version": template.version})


@router.post("/admin/waiver/reset", auth=admin_auth, response={201: dict})
def reset(request, body: ResetBody):
    if not body.reason.strip():
        raise HttpError(400, "a reason is required")
    reset_row = service.reset_signatures(request.auth, body.reason)
    return Status(201, {"reset_at": reset_row.reset_at.isoformat()})
