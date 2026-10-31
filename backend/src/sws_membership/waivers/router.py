"""Reading, signing, publishing and resetting the waiver."""

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from sws_membership.auth.dependencies import (
    CurrentMember,
    DatabaseSession,
    StorageDependency,
    require_role,
)
from sws_membership.members.models import Member, MemberRole
from sws_membership.waivers import service

router = APIRouter(prefix="/api", tags=["waivers"])


class WaiverView(BaseModel):
    template_id: int | None
    version: int | None
    title: str | None
    body_text: str | None
    document_hash: str | None
    signed: bool
    signed_at: datetime | None
    needs_guardian: bool


class SignatureBody(BaseModel):
    template_id: int
    signer_name: str
    signature_png: str
    guardian_name: str | None = None
    guardian_signature_png: str | None = None


class PublishBody(BaseModel):
    title: str
    body_text: str


class ResetBody(BaseModel):
    reason: str


def _view(session, member: Member) -> WaiverView:
    template = service.current_template(session)
    signature = service.current_signature(session, member) if template else None
    return WaiverView(
        template_id=template.id if template else None,
        version=template.version if template else None,
        title=template.title if template else None,
        body_text=template.body_text if template else None,
        document_hash=template.document_hash if template else None,
        signed=signature is not None,
        signed_at=signature.signed_at if signature else None,
        needs_guardian=service.needs_guardian(member, date.today()),
    )


@router.get("/waiver")
def waiver(session: DatabaseSession, member: CurrentMember) -> WaiverView:
    return _view(session, member)


@router.post("/waiver/sign", status_code=status.HTTP_201_CREATED)
def sign(
    body: SignatureBody,
    request: Request,
    session: DatabaseSession,
    member: CurrentMember,
    storage: StorageDependency,
) -> WaiverView:
    try:
        service.sign(
            session,
            storage,
            member,
            body.template_id,
            service.SignatureInput(
                signer_name=body.signer_name,
                signature_png=body.signature_png,
                guardian_name=body.guardian_name,
                guardian_signature_png=body.guardian_signature_png,
            ),
            ip_address=request.client.host if request.client else "unknown",
        )
    except service.SignatureRejected as why:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(why))
    return _view(session, member)


Admin = Annotated[Member, Depends(require_role(MemberRole.ADMIN))]


@router.post("/admin/waiver/publish", status_code=status.HTTP_201_CREATED)
def publish(body: PublishBody, session: DatabaseSession, admin: Admin) -> dict:
    if not body.title.strip() or not body.body_text.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "title and text are required")
    template = service.publish_template(session, body.title, body.body_text, by=admin)
    return {"template_id": template.id, "version": template.version}


@router.post("/admin/waiver/reset", status_code=status.HTTP_201_CREATED)
def reset(body: ResetBody, session: DatabaseSession, admin: Admin) -> dict:
    if not body.reason.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "a reason is required")
    reset_row = service.reset_signatures(session, admin, body.reason)
    return {"reset_at": reset_row.reset_at.isoformat()}
