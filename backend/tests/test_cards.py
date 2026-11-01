from datetime import date

import pytest

from sws_membership.cards.models import CardPrint
from sws_membership.cards.render import CardData, render_cards
from sws_membership.catalog.models import Product
from sws_membership.catalog.sample_data import load_sample_catalog
from sws_membership.entitlements.models import Entitlement, EntitlementKind
from sws_membership.members.models import MemberRole
from tests.conftest import make_member

pytestmark = pytest.mark.django_db

YEAR = 2026
TODAY = date(YEAR, 6, 15)


def _member(email, number=None, roles=()):
    fields = {"first_name": "Card", "last_name": "Holder"}
    if number:
        fields["member_number"] = number
    return make_member(email, roles=roles, **fields)


def _membership(member):
    load_sample_catalog(YEAR)
    Entitlement.objects.create(
        member=member,
        kind=EntitlementKind.MEMBERSHIP,
        product=Product.objects.get(name=f"Adult SWS Membership {YEAR}"),
        valid_from=date(YEAR, 1, 1),
        valid_to=date(YEAR, 12, 31),
    )


def test_render_produces_a_pdf_with_two_pages_per_card():
    cards = [
        CardData(
            4242, "Sam", "Rider", "2026 member", "Kite, foil", "https://example.com/shuttle", TODAY
        ),
        CardData(
            7, "Pat", "Ridley", "No current membership", "", "https://example.com/shuttle", TODAY
        ),
    ]
    data = render_cards(cards)
    assert data.startswith(b"%PDF")
    assert data.count(b"/Type /Page\n") + data.count(b"/Type /Page>") >= 4 or b"/Count 4" in data


def test_member_downloads_their_own_card(client, pin_today):
    member = _member("own@example.com", number=4242)
    _membership(member)
    client.sign_in(member)
    pin_today(TODAY)
    response = client.get("/api/me/card.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "sws-card-4242.pdf" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")


def test_staff_batch_print_records_each_card(client):
    staff = _member("staff@example.com", roles=[MemberRole.STAFF])
    a = _member("a@example.com")
    b = _member("b@example.com")
    client.sign_in(staff)
    response = client.post_json("/api/staff/cards/print", {"member_ids": [b.id, a.id]})
    assert response.status_code == 200 and response.content.startswith(b"%PDF")
    prints = CardPrint.objects.order_by("id")
    assert [(p.member_id, p.printed_by_id) for p in prints] == [(b.id, staff.id), (a.id, staff.id)]
    assert client.post_json("/api/staff/cards/print", {"member_ids": [999999]}).status_code == 404
    assert client.post_json("/api/staff/cards/print", {"member_ids": []}).status_code == 400


def test_plain_members_cannot_batch_print(client):
    client.sign_in(_member("plain@example.com"))
    assert client.post_json("/api/staff/cards/print", {"member_ids": [1]}).status_code == 403
