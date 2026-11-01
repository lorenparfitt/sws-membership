"""Products, their prices, the entitlements they grant, and the rules that gate them.

The split follows the shape Stripe settled on: a Product is one sellable
thing, a Price is an amount with a window, and what the purchase confers is
separate from both. Rules are data rows that pick a rule kind from the
closed list in eligibility.py and carry its parameters.
"""

from django.db import models

from sws_membership.entitlements.models import EntitlementKind

CURRENCY = "CAD"


class RuleKind(models.TextChoices):
    """The closed list of conditions a product can be gated behind."""

    REQUIRES_ACTIVE_ENTITLEMENT = "requires_active_entitlement", "Requires an active entitlement"
    REQUIRES_CURRENT_WAIVER = "requires_current_waiver", "Requires the current waiver"
    PROFILE_COMPLETE = "profile_complete", "Profile complete"
    AGE_AT_LEAST = "age_at_least", "Age at least"
    AGE_AT_MOST = "age_at_most", "Age at most"
    ONE_PER_MEMBER_PER_SEASON = "one_per_member_per_season", "One per member per season"


class Product(models.Model):
    name = models.CharField(max_length=120)
    description = models.TextField(default="", blank=True)
    season_year = models.IntegerField(db_index=True)
    sort_order = models.IntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "products"
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name

    def spec(self):
        """The product as the pure eligibility engine reads it."""
        from sws_membership.catalog.eligibility import GrantSpec, PriceSpec, ProductSpec, RuleSpec

        return ProductSpec(
            id=self.id,
            name=self.name,
            season_year=self.season_year,
            prices=tuple(
                PriceSpec(
                    id=p.id,
                    label=p.label,
                    amount_cents=p.amount_cents,
                    starts_at=p.starts_at,
                    ends_at=p.ends_at,
                    members_only=p.members_only,
                )
                for p in self.prices.all()
            ),
            grants=tuple(
                GrantSpec(
                    kind=EntitlementKind(g.kind),
                    valid_from=g.valid_from,
                    valid_to=g.valid_to,
                    visit_count=g.visit_count,
                )
                for g in self.grants.all()
            ),
            rules=tuple(
                RuleSpec(
                    kind=RuleKind(r.kind),
                    parameters=r.parameters,
                    failure_message=r.failure_message,
                )
                for r in self.rules.all()
            ),
        )


def products_for_sale():
    return Product.objects.filter(active=True).prefetch_related("prices", "grants", "rules")


class Price(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="prices")
    label = models.CharField(max_length=60, default="", blank=True)
    amount_cents = models.IntegerField()
    starts_at = models.DateField()
    ends_at = models.DateField(null=True, blank=True)
    members_only = models.BooleanField(default=False)

    class Meta:
        db_table = "prices"
        ordering = ["starts_at", "id"]

    def __str__(self) -> str:
        return f"{self.label} {self.amount_cents / 100:.2f}"

    def order_lines_exist(self) -> bool:
        from sws_membership.orders.models import OrderLine

        return OrderLine.objects.filter(price_id=self.id).exists()


class EntitlementGrant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="grants")
    kind = models.CharField(max_length=20, choices=EntitlementKind.choices)
    valid_from = models.DateField()
    valid_to = models.DateField()
    visit_count = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = "entitlement_grants"
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.kind} {self.valid_from}..{self.valid_to}"


class EligibilityRule(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="rules")
    kind = models.CharField(max_length=40, choices=RuleKind.choices)
    parameters = models.JSONField(default=dict, blank=True)
    failure_message = models.CharField(max_length=200)

    class Meta:
        db_table = "eligibility_rules"
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.kind} {self.parameters}"
