"""Member face photos: validated, normalised, and stored behind the storage seam.

Whatever the phone or camera sends, what is kept is a JPEG no larger than
PHOTO_SIZE on its long side with all metadata dropped, so a photo never
carries location data and the card renderer gets one predictable format.
"""

from datetime import UTC, datetime
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session

from sws_membership.members.models import Member
from sws_membership.storage.objects import ObjectStorage

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
PHOTO_SIZE = 600
ACCEPTED = {"JPEG", "PNG", "WEBP", "HEIF"}


class PhotoRejected(ValueError):
    pass


def normalise_photo(data: bytes) -> bytes:
    if len(data) > MAX_UPLOAD_BYTES:
        raise PhotoRejected(f"photo is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
    try:
        image = Image.open(BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError):
        raise PhotoRejected("that file is not an image") from None
    if image.format not in ACCEPTED:
        raise PhotoRejected(f"unsupported image type {image.format}")
    image = ImageOps.exif_transpose(image).convert("RGB")
    image.thumbnail((PHOTO_SIZE, PHOTO_SIZE))
    out = BytesIO()
    image.save(out, "JPEG", quality=85, optimize=True)
    return out.getvalue()


def store_photo(session: Session, storage: ObjectStorage, member: Member, data: bytes) -> str:
    jpeg = normalise_photo(data)
    key = f"photos/{member.id}/{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')}.jpg"
    storage.put(key, jpeg, "image/jpeg")
    member.photo_key = key
    session.flush()
    return key
