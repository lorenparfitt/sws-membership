"""Profile and photo routes: a member's own, and staff on behalf of anyone."""

from datetime import date

from django.http import HttpResponse
from ninja import File, Router, Schema
from ninja.errors import HttpError
from ninja.files import UploadedFile

from sws_membership.accounts.auth import member_auth, staff_auth
from sws_membership.members import photos, profile
from sws_membership.members.models import SPORT_LABELS, Member, Sport
from sws_membership.wiring import wiring

router = Router(tags=["members"])


class ProfileView(Schema):
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
            sports=member.sport_values(),
            has_photo=member.photo_key is not None,
            missing=member.missing_profile_fields(),
        )


class ProfileBody(Schema):
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


def load_member(member_id: int) -> Member:
    member = Member.objects.filter(id=member_id).first()
    if member is None:
        raise HttpError(404, "no such member")
    return member


@router.get("/sports", auth=None)
def sports(request) -> list[dict[str, str]]:
    return [{"value": sport.value, "label": SPORT_LABELS[sport]} for sport in Sport]


@router.get("/me/profile", auth=member_auth, response=ProfileView)
def my_profile(request):
    return ProfileView.of(request.auth)


@router.put("/me/profile", auth=member_auth, response=ProfileView)
def update_my_profile(request, body: ProfileBody):
    try:
        profile.update_profile(
            request.auth,
            profile.ProfileInput(**body.dict(exclude={"sports"}), sports=tuple(body.sports)),
        )
    except profile.ProfileRejected as why:
        raise HttpError(400, str(why))
    return ProfileView.of(request.auth)


def _read_upload(upload: UploadedFile) -> bytes:
    if upload.size > photos.MAX_UPLOAD_BYTES:
        raise HttpError(413, "photo too large")
    return upload.read()


def _store(member: Member, data: bytes) -> ProfileView:
    try:
        photos.store_photo(wiring.storage, member, data)
    except photos.PhotoRejected as why:
        raise HttpError(400, str(why))
    return ProfileView.of(member)


def _photo_response(member: Member) -> HttpResponse:
    if not member.photo_key:
        raise HttpError(404, "no photo")
    response = HttpResponse(wiring.storage.get(member.photo_key), content_type="image/jpeg")
    response["Cache-Control"] = "private, max-age=60"
    return response


@router.post("/me/photo", auth=member_auth, response=ProfileView)
def upload_my_photo(request, photo: File[UploadedFile]):
    return _store(request.auth, _read_upload(photo))


@router.get("/me/photo", auth=member_auth)
def my_photo(request):
    return _photo_response(request.auth)


@router.get("/staff/members/{member_id}/photo", auth=staff_auth)
def member_photo(request, member_id: int):
    return _photo_response(load_member(member_id))


@router.post("/staff/members/{member_id}/photo", auth=staff_auth, response=ProfileView)
def upload_member_photo(request, member_id: int, photo: File[UploadedFile]):
    return _store(load_member(member_id), _read_upload(photo))
