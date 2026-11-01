"""One row per card printed, so staff can see who still needs one."""

from django.conf import settings
from django.db import models


class CardPrint(models.Model):
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="card_prints"
    )
    printed_at = models.DateTimeField(auto_now_add=True)
    printed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        db_table = "card_prints"

    def __str__(self) -> str:
        return f"{self.member_id} printed {self.printed_at:%Y-%m-%d}"
