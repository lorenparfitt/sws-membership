"""Profile and photo routes: a member's own, and staff on behalf of anyone."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status
from pydantic import BaseModel

from sws_membership.auth.dependencies import (
    CurrentMember,
    DatabaseSession,
    StorageDependency,
    require_role,
)
from sws_membership.members import photos, profile
from sws_membership.members.models import SPORT_LABELS, Member, MemberRole, Sport

router = APIRouter(prefix="/api", tags=["members"])

Staff = Annotated[Member, Depends(require_role(MemberRole.STAFF))]


class ProfileView(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone: str | None
    date_of_birth: date | None
    address_line_1: str | None
    address_line_2: str | None
    city: str | None
    province: str | None
    postal_code: str | None
    sports: list[str]
    has_photo: bool
    missing: list[str]

    @classmethod
    def of(cls, member: Member) -> "ProfileView":
        return cls(
            first_name=member.first_name,
            last_name=member.last_name,
            email=member.email,
            phone=member.phone,
            date_of_birth=member.date_of_birth,
            address_line_1=member.address_line_1,
            address_line_2=member.address_line_2,
            city=member.city,
            province=member.province,
            postal_code=member.postal_code,
            sports=sorted(row.sport.value for row in member.sports),
            has_photo=member.photo_key is not None,
            missing=member.missing_profile_fields(),
        )


class ProfileBody(BaseModel):
    first_name: str
    last_name: str
    phone: str | None = None
    date_of_birth: date | None = None
    address_line_1: str | None = None
    address_line_2: str | None = None
    city: str | None = None
    province: str | None = None
    postal_code: str | None = None
    sports: list[Sport] = []


@router.get("/sports")
def sports() -> list[dict[str, str]]:
    return [{"value": sport.value, "label": SPORT_LABELS[sport]} for sport in Sport]


@router.get("/me/profile")
def my_profile(member: CurrentMember) -> ProfileView:
    return ProfileView.of(member)


@router.put("/me/profile")
def update_my_profile(
    body: ProfileBody, session: DatabaseSession, member: CurrentMember
) -> ProfileView:
    try:
        profile.update_profile(
            session,
            member,
            profile.ProfileInput(**body.model_dump(exclude={"sports"}), sports=tuple(body.sports)),
        )
    except profile.ProfileRejected as why:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(why))
    return ProfileView.of(member)


async def _read_upload(upload: UploadFile) -> bytes:
    data = await upload.read(photos.MAX_UPLOAD_BYTES + 1)
    if len(data) > photos.MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "photo too large")
    return data


def _store(session, storage, member: Member, data: bytes) -> ProfileView:
    try:
        photos.store_photo(session, storage, member, data)
    except photos.PhotoRejected as why:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(why))
    return ProfileView.of(member)


def _photo_response(storage, member: Member) -> Response:
    if not member.photo_key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no photo")
    return Response(
        content=storage.get(member.photo_key),
        media_type="image/jpeg",
        headers={"cache-control": "private, max-age=60"},
    )


@router.post("/me/photo")
async def upload_my_photo(
    photo: UploadFile, session: DatabaseSession, member: CurrentMember, storage: StorageDependency
) -> ProfileView:
    return _store(session, storage, member, await _read_upload(photo))


@router.get("/me/photo")
def my_photo(member: CurrentMember, storage: StorageDependency) -> Response:
    return _photo_response(storage, member)


@router.get("/staff/members/{member_id}/photo")
def member_photo(
    member_id: int, session: DatabaseSession, storage: StorageDependency, staff: Staff
) -> Response:
    member = session.get(Member, member_id)
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such member")
    return _photo_response(storage, member)


@router.post("/staff/members/{member_id}/photo")
async def upload_member_photo(
    member_id: int,
    photo: UploadFile,
    session: DatabaseSession,
    storage: StorageDependency,
    staff: Staff,
) -> ProfileView:
    member = session.get(Member, member_id)
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such member")
    return _store(session, storage, member, await _read_upload(photo))
