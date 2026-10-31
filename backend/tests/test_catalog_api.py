from datetime import date

from sqlalchemy import select

from sws_membership.auth import service
from sws_membership.auth.dependencies import SESSION_COOKIE
from sws_membership.catalog.models import Product
from sws_membership.catalog.router import current_day
from sws_membership.catalog.sample_data import load_sample_catalog
from sws_membership.entitlements.models import Entitlement, EntitlementKind
from sws_membership.members.member_numbers import allocate_member_number
from sws_membership.members.models import Member
from tests.conftest import make_eligible

YEAR = 2026
TODAY = date(YEAR, 6, 15)


def _signed_in(session, client, birth: date) -> Member:
    member = Member(
        member_number=allocate_member_number(session),
        first_name="Cat",
        last_name="Log",
        email="catalog@example.com",
        date_of_birth=birth,
    )
    session.add(member)
    session.flush()
    make_eligible(session, member)
    client.cookies.set(SESSION_COOKIE, service.open_session(session, member))
    client.app.dependency_overrides[current_day] = lambda: TODAY
    return member


def _by_name(body):
    return {product["name"]: product for product in body}


def test_catalog_requires_sign_in(client):
    assert client.get("/api/catalog").status_code == 401


def test_sample_catalog_loads_once_and_resyncs_rules(session):
    assert load_sample_catalog(session, YEAR) == 6
    day_pass = session.scalars(select(Product).where(Product.name == f"Day Pass {YEAR}")).one()
    day_pass.rules.clear()
    session.flush()
    assert load_sample_catalog(session, YEAR) == 0
    session.refresh(day_pass)
    assert [rule.kind.value for rule in day_pass.rules] == [
        "profile_complete",
        "requires_current_waiver",
    ]


def test_adult_without_membership_sees_the_gates(session, client):
    load_sample_catalog(session, YEAR)
    _signed_in(session, client, date(1990, 1, 1))
    body = _by_name(client.get("/api/catalog").json())
    assert len(body) == 6

    membership = body[f"Adult SWS Membership {YEAR}"]
    assert membership["purchasable"] is True
    assert membership["price"]["amount_cents"] == 4000
    assert membership["grants"] == ["membership"]

    assert body[f"Youth SWS Membership {YEAR}"]["locked_because"] == ["For members 18 and under"]

    season = body[f"Adult Season Pass {YEAR}"]
    assert season["price"]["label"] == "Regular"  # early bird ended April 30

    shuttle = body[f"Member Day Shuttle Pass {YEAR}"]
    assert shuttle["purchasable"] is False
    assert shuttle["price"] is None  # the only price is members-only
    assert f"Needs an active {YEAR} membership" in shuttle["locked_because"]
    assert "not on sale today" in shuttle["locked_because"]


def test_membership_unlocks_the_shuttle_pass_and_blocks_a_repeat_purchase(session, client):
    load_sample_catalog(session, YEAR)
    member = _signed_in(session, client, date(1990, 1, 1))
    membership_product = session.scalars(
        select(Product).where(Product.name == f"Adult SWS Membership {YEAR}")
    ).one()
    session.add(
        Entitlement(
            member_id=member.id,
            kind=EntitlementKind.MEMBERSHIP,
            product_id=membership_product.id,
            valid_from=date(YEAR, 1, 1),
            valid_to=date(YEAR, 12, 31),
        )
    )
    session.flush()

    body = _by_name(client.get("/api/catalog").json())
    shuttle = body[f"Member Day Shuttle Pass {YEAR}"]
    assert shuttle["purchasable"] is True
    assert shuttle["price"]["members_only"] is True
    assert shuttle["price"]["amount_cents"] == 2500

    again = body[f"Adult SWS Membership {YEAR}"]
    assert again["purchasable"] is False
    assert again["locked_because"] == ["Already held for this season"]


def test_a_youth_is_offered_youth_products_only(session, client):
    load_sample_catalog(session, YEAR)
    _signed_in(session, client, date(YEAR - 15, 3, 3))
    body = _by_name(client.get("/api/catalog").json())
    assert body[f"Youth Season Pass {YEAR}"]["purchasable"] is True
    assert body[f"Adult Season Pass {YEAR}"]["locked_because"] == ["For members 19 and over"]
    assert body[f"Day Pass {YEAR}"]["purchasable"] is True


def test_a_membership_in_the_basket_unlocks_the_shuttle_pass_before_payment(session, client):
    load_sample_catalog(session, YEAR)
    _signed_in(session, client, date(1990, 1, 1))
    membership = session.scalars(
        select(Product).where(Product.name == f"Adult SWS Membership {YEAR}")
    ).one()

    body = _by_name(client.get("/api/catalog", params={"basket": [membership.id]}).json())
    shuttle = body[f"Member Day Shuttle Pass {YEAR}"]
    assert shuttle["purchasable"] is True
    assert shuttle["price"]["amount_cents"] == 2500
    # The membership itself is judged without its own grant: still purchasable.
    assert body[f"Adult SWS Membership {YEAR}"]["purchasable"] is True

    without = _by_name(client.get("/api/catalog").json())
    assert without[f"Member Day Shuttle Pass {YEAR}"]["purchasable"] is False
