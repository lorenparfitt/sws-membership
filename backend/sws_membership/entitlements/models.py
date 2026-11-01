"""Entitlements: typed rights with a validity window, one row per grant."""

from datetime import date

from django.conf import settings
from django.db import models


class EntitlementKind(models.TextChoices):
    """The closed list of rights a product can confer."""

    MEMBERSHIP = "membership", "Membership"
    SEASON_ACCESS = "season_access", "Season access"
    DAY_VISITS = "day_visits", "Day visits"
    SHUTTLE_ACCESS = "shuttle_access", "Shuttle access"


def active_on(kind: str, valid_from: date, valid_to: date, visits_remaining, day: date) -> bool:
    """One rule for rows and for what a basket would grant."""
    if not (valid_from <= day <= valid_to):
        return False
    if kind == EntitlementKind.DAY_VISITS:
        return (visits_remaining or 0) > 0
    return True


class Entitlement(models.Model):
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="entitlements"
    )
    kind = models.CharField(max_length=20, choices=EntitlementKind.choices)
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT)
    valid_from = models.DateField()
    valid_to = models.DateField()
    # Only for DAY_VISITS: how many visits are left to consume.
    visits_remaining = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "entitlements"

    def __str__(self) -> str:
        return f"{self.kind} {self.valid_from}..{self.valid_to} (member {self.member_id})"

    def is_active_on(self, day: date) -> bool:
        return active_on(self.kind, self.valid_from, self.valid_to, self.visits_remaining, day)
