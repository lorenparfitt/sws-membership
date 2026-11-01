"""Editing the member profile: the fields a member keeps current themselves."""

from dataclasses import dataclass
from datetime import date

from sws_membership.members.models import Member, MemberSport, Sport


@dataclass(frozen=True)
class ProfileInput:
    first_name: str
    last_name: str
    phone: str | None
    date_of_birth: date | None
    address_line_1: str | None
    address_line_2: str | None
    city: str | None
    province: str | None
    postal_code: str | None
    sports: tuple[Sport, ...]


class ProfileRejected(ValueError):
    pass


def _clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def set_sports(member: Member, sports: tuple[Sport, ...] | set[Sport]) -> None:
    wanted = set(sports)
    member.sports.exclude(sport__in=wanted).delete()
    held = set(member.sports.values_list("sport", flat=True))
    MemberSport.objects.bulk_create(MemberSport(member=member, sport=s) for s in wanted - held)


def update_profile(member: Member, given: ProfileInput) -> Member:
    """Apply the fields. The birth date, once set, is only changed by staff."""
    if not given.first_name.strip() or not given.last_name.strip():
        raise ProfileRejected("first and last name are required")
    if member.date_of_birth is not None and given.date_of_birth != member.date_of_birth:
        raise ProfileRejected("date of birth is set; ask staff to correct it")
    if given.date_of_birth is not None and given.date_of_birth > date.today():
        raise ProfileRejected("date of birth is in the future")
    member.first_name = given.first_name.strip()
    member.last_name = given.last_name.strip()
    member.phone = _clean(given.phone)
    if member.date_of_birth is None:
        member.date_of_birth = given.date_of_birth
    member.address_line_1 = _clean(given.address_line_1)
    member.address_line_2 = _clean(given.address_line_2)
    member.city = _clean(given.city)
    member.province = _clean(given.province)
    member.postal_code = _clean(given.postal_code)
    member.save()
    set_sports(member, given.sports)
    return member
