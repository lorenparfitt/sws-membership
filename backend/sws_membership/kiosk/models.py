"""Check-ins: one row per admission, naming the entitlement that admitted."""

from django.conf import settings
from django.db import models


class Station(models.TextChoices):
    """Where a check-in happens. Each station admits on its own entitlement kinds."""

    SPIT = "spit", "Spit"
    SHUTTLE = "shuttle", "Shuttle"


class CheckIn(models.Model):
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="check_ins"
    )
    entitlement = models.ForeignKey("entitlements.Entitlement", on_delete=models.PROTECT)
    station = models.CharField(max_length=20, choices=Station.choices)
    # The local calendar day, so one check-in per day is a plain unique rule.
    on_day = models.DateField(db_index=True)
    checked_in_at = models.DateTimeField(auto_now_add=True)
    checked_in_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        db_table = "check_ins"
        constraints = [
            models.UniqueConstraint(
                fields=["member", "station", "on_day"], name="check_ins_once_per_station_day"
            )
        ]

    def __str__(self) -> str:
        return f"{self.member_id} {self.station} {self.on_day}"
