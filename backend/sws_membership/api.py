"""The JSON API: one NinjaAPI with a router per area. Wiring only."""

from django.conf import settings
from ninja import NinjaAPI

from sws_membership.accounts.api import router as accounts_router
from sws_membership.backoffice.api import router as backoffice_router
from sws_membership.cards.api import router as cards_router
from sws_membership.catalog.api import router as catalog_router
from sws_membership.entitlements.api import router as entitlements_router
from sws_membership.errors import Refused, install_error_handlers
from sws_membership.kiosk.api import router as kiosk_router
from sws_membership.members.api import router as members_router
from sws_membership.members.staff_api import router as staff_members_router
from sws_membership.orders.api import router as orders_router
from sws_membership.waivers.api import router as waivers_router

api = NinjaAPI(title="SWS Membership", version="0.2", urls_namespace="api")
install_error_handlers(api)

api.add_router("/auth", accounts_router)
api.add_router("", members_router)
api.add_router("/catalog", catalog_router)
api.add_router("/entitlements", entitlements_router)
api.add_router("", waivers_router)
api.add_router("/staff/kiosk", kiosk_router)
api.add_router("", cards_router)
api.add_router("", orders_router)
api.add_router("/staff/members", staff_members_router)
api.add_router("/admin", backoffice_router)
if settings.SWS_PAYMENT_PROCESSOR == "fake":
    from sws_membership.payments.fake_api import router as fake_payments_router

    api.add_router("/payments/fake", fake_payments_router)

__all__ = ["Refused", "api", "settings"]
