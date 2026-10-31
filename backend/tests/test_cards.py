from datetime import date

from sqlalchemy import select

from sws_membership.auth import service as auth
from sws_membership.auth.dependencies import SESSION_COOKIE
from sws_membership.cards.models import CardPrint
from sws_membership.cards.render import CardData, render_cards
from sws_membership.catalog.models import Product
from sws_membership.catalog.router import current_day
from sws_membership.catalog.sample_data import load_sample_catalog
from sws_membership.entitlements.models import Entitlement, EntitlementKind
from sws_membership.members.member_numbers import allocate_member_number
from sws_membership.members.models import Member, MemberRole, MemberRoleAssignment

YEAR = 2026
TODAY = date(YEAR, 6, 15)


def _member(session, email, number=None, roles=()) -> Member:
    member = Member(
        member_number=number or allocate_member_number(session),
        first_name="Card",
        last_name="Holder",
        email=email,
        roles=[MemberRoleAssignment(role=r) for r in roles],
    )
    session.add(member)
    session.flush()
    return member


def _membership(session, member):
    load_sample_catalog(session, YEAR)
    product = session.scalars(
        select(Product).where(Product.name == f"Adult SWS Membership {YEAR}")
    ).one()
    session.add(
        Entitlement(
            member_id=member.id,
            kind=EntitlementKind.MEMBERSHIP,
            product_id=product.id,
            valid_from=date(YEAR, 1, 1),
            valid_to=date(YEAR, 12, 31),
        )
    )
    session.flush()


def _sign_in(session, client, member):
    client.cookies.set(SESSION_COOKIE, auth.open_session(session, member))
    client.app.dependency_overrides[current_day] = lambda: TODAY


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


def test_member_downloads_their_own_card(session, client):
    member = _member(session, "own@example.com", number=4242)
    _membership(session, member)
    _sign_in(session, client, member)
    response = client.get("/api/me/card.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "sws-card-4242.pdf" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")


def test_staff_batch_print_records_each_card(session, client):
    staff = _member(session, "staff@example.com", roles=[MemberRole.STAFF])
    a = _member(session, "a@example.com")
    b = _member(session, "b@example.com")
    _sign_in(session, client, staff)
    response = client.post("/api/staff/cards/print", json={"member_ids": [b.id, a.id]})
    assert response.status_code == 200 and response.content.startswith(b"%PDF")
    prints = session.scalars(select(CardPrint).order_by(CardPrint.id)).all()
    assert [(p.member_id, p.printed_by_member_id) for p in prints] == [
        (b.id, staff.id),
        (a.id, staff.id),
    ]
    assert client.post("/api/staff/cards/print", json={"member_ids": [999999]}).status_code == 404
    assert client.post("/api/staff/cards/print", json={"member_ids": []}).status_code == 400


def test_plain_members_cannot_batch_print(session, client):
    _sign_in(session, client, _member(session, "plain@example.com"))
    assert client.post("/api/staff/cards/print", json={"member_ids": [1]}).status_code == 403
