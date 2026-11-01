"""Card downloads: a member's own, and staff prints for anyone."""

from django.conf import settings
from django.http import HttpResponse
from ninja import Router, Schema
from ninja.errors import HttpError

from sws_membership import clock
from sws_membership.accounts.auth import member_auth, staff_auth
from sws_membership.cards import service
from sws_membership.members.models import Member
from sws_membership.wiring import wiring

router = Router(tags=["cards"])


def _pdf(data: bytes, filename: str) -> HttpResponse:
    response = HttpResponse(data, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


@router.get("/me/card.pdf", auth=member_auth)
def my_card(request):
    member = request.auth
    data = service.render_for_members(
        wiring.storage, [member], clock.today(), settings.SWS_SHUTTLE_URL
    )
    return _pdf(data, f"sws-card-{member.member_number}.pdf")


class BatchBody(Schema):
    member_ids: list[int]


@router.post("/staff/cards/print", auth=staff_auth)
def print_cards(request, body: BatchBody):
    """A PDF for the given members, and a print record for each."""
    if not body.member_ids:
        raise HttpError(400, "no members selected")
    members = list(Member.objects.filter(id__in=body.member_ids))
    missing = set(body.member_ids) - {m.id for m in members}
    if missing:
        raise HttpError(404, f"no such members: {sorted(missing)}")
    ordered = sorted(members, key=lambda m: body.member_ids.index(m.id))
    data = service.render_for_members(
        wiring.storage, ordered, clock.today(), settings.SWS_SHUTTLE_URL
    )
    service.record_prints(ordered, request.auth)
    return _pdf(data, "sws-cards.pdf")
