"""docs/api.md is generated from the routes; this keeps the committed copy honest."""

from pathlib import Path

from sws_membership.api_doc import render_api_doc, routes_of

DOC = Path(__file__).resolve().parents[2] / "docs" / "api.md"


def test_the_committed_api_doc_matches_the_routes():
    assert DOC.read_text() == render_api_doc(), "docs/api.md is stale: run uv run doit api_doc"


def test_every_route_states_who_may_call_it_and_what_it_does():
    from sws_membership.api import api

    for route in routes_of(api):
        assert route.role in {"none", "member", "staff", "admin"}, route
        assert route.does and route.does[0].isupper(), route


def test_the_roles_come_from_the_auth_classes_not_the_path():
    from sws_membership.api import api

    by_path = {(r.method, r.path): r.role for r in routes_of(api)}
    assert by_path[("GET", "/api/catalog")] == "member"
    assert by_path[("POST", "/api/staff/orders")] == "staff"
    assert by_path[("POST", "/api/admin/orders/{order_id}/refund")] == "admin"
    assert by_path[("GET", "/api/admin/catalog/products")] == "admin"
    assert by_path[("PUT", "/api/staff/members/{member_id}/roles")] == "admin"
    assert by_path[("POST", "/api/payments/notification")] == "none"
