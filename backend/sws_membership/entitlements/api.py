"""What the signed-in member holds."""

from datetime import date

from ninja import Router, Schema

from sws_membership import clock
from sws_membership.accounts.auth import member_auth
from sws_membership.entitlements.models import Entitlement

router = Router(tags=["entitlements"])


class EntitlementView(Schema):
    id: int
    kind: str
    product_name: str
    valid_from: date
    valid_to: date
    visits_remaining: int | None
    active: bool

    @classmethod
    def of(cls, row: Entitlement, today: date) -> "EntitlementView":
        return cls(
            id=row.id,
            kind=row.kind,
            product_name=row.product.name,
            valid_from=row.valid_from,
            valid_to=row.valid_to,
            visits_remaining=row.visits_remaining,
            active=row.is_active_on(today),
        )


def entitlements_of(member):
    return member.entitlements.select_related("product").order_by("-valid_to", "id")


@router.get("", auth=member_auth, response=list[EntitlementView])
def my_entitlements(request):
    today = clock.today()
    return [EntitlementView.of(row, today) for row in entitlements_of(request.auth)]
