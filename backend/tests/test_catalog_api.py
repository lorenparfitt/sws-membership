from datetime import date

import pytest

from sws_membership.catalog.models import Product
from sws_membership.catalog.sample_data import load_sample_catalog
from sws_membership.entitlements.models import Entitlement, EntitlementKind
from tests.conftest import make_eligible, make_member

pytestmark = pytest.mark.django_db

YEAR = 2026
TODAY = date(YEAR, 6, 15)


def _signed_in(client, pin_today, birth: date):
    member = make_member(
        "catalog@example.com", first_name="Cat", last_name="Log", date_of_birth=birth
    )
    make_eligible(member)
    client.sign_in(member)
    pin_today(TODAY)
    return member


def _by_name(body):
    return {product["name"]: product for product in body}


def test_catalog_requires_sign_in(client):
    assert client.get("/api/catalog").status_code == 401


def test_sample_catalog_loads_once_and_resyncs_rules():
    assert load_sample_catalog(YEAR) == 6
    day_pass = Product.objects.get(name=f"Day Pass {YEAR}")
    day_pass.rules.all().delete()
    assert load_sample_catalog(YEAR) == 0
    assert [rule.kind for rule in day_pass.rules.all()] == [
        "profile_complete",
        "requires_current_waiver",
    ]


def test_adult_without_membership_sees_the_gates(client, pin_today):
    load_sample_catalog(YEAR)
    _signed_in(client, pin_today, date(1990, 1, 1))
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


def test_membership_unlocks_the_shuttle_pass_and_blocks_a_repeat_purchase(client, pin_today):
    load_sample_catalog(YEAR)
    member = _signed_in(client, pin_today, date(1990, 1, 1))
    membership_product = Product.objects.get(name=f"Adult SWS Membership {YEAR}")
    Entitlement.objects.create(
        member=member,
        kind=EntitlementKind.MEMBERSHIP,
        product=membership_product,
        valid_from=date(YEAR, 1, 1),
        valid_to=date(YEAR, 12, 31),
    )

    body = _by_name(client.get("/api/catalog").json())
    shuttle = body[f"Member Day Shuttle Pass {YEAR}"]
    assert shuttle["purchasable"] is True
    assert shuttle["price"]["members_only"] is True
    assert shuttle["price"]["amount_cents"] == 2500

    again = body[f"Adult SWS Membership {YEAR}"]
    assert again["purchasable"] is False
    assert again["locked_because"] == ["Already held for this season"]


def test_a_youth_is_offered_youth_products_only(client, pin_today):
    load_sample_catalog(YEAR)
    _signed_in(client, pin_today, date(YEAR - 15, 3, 3))
    body = _by_name(client.get("/api/catalog").json())
    assert body[f"Youth Season Pass {YEAR}"]["purchasable"] is True
    assert body[f"Adult Season Pass {YEAR}"]["locked_because"] == ["For members 19 and over"]
    assert body[f"Day Pass {YEAR}"]["purchasable"] is True


def test_a_membership_in_the_basket_unlocks_the_shuttle_pass_before_payment(client, pin_today):
    load_sample_catalog(YEAR)
    _signed_in(client, pin_today, date(1990, 1, 1))
    membership = Product.objects.get(name=f"Adult SWS Membership {YEAR}")

    body = _by_name(client.get("/api/catalog", {"basket": [membership.id]}).json())
    shuttle = body[f"Member Day Shuttle Pass {YEAR}"]
    assert shuttle["purchasable"] is True
    assert shuttle["price"]["amount_cents"] == 2500
    # The membership itself is judged without its own grant: still purchasable.
    assert body[f"Adult SWS Membership {YEAR}"]["purchasable"] is True

    without = _by_name(client.get("/api/catalog").json())
    assert without[f"Member Day Shuttle Pass {YEAR}"]["purchasable"] is False


def test_my_entitlements_lists_what_is_held(client, pin_today):
    load_sample_catalog(YEAR)
    member = _signed_in(client, pin_today, date(1990, 1, 1))
    assert client.get("/api/entitlements").json() == []
    Entitlement.objects.create(
        member=member,
        kind=EntitlementKind.DAY_VISITS,
        product=Product.objects.get(name=f"Day Pass {YEAR}"),
        valid_from=date(YEAR, 1, 1),
        valid_to=date(YEAR, 12, 31),
        visits_remaining=1,
    )
    [row] = client.get("/api/entitlements").json()
    assert (row["kind"], row["visits_remaining"], row["active"]) == ("day_visits", 1, True)
