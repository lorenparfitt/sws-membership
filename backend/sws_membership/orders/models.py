"""Orders, their lines, and the payments recorded against them."""

from django.conf import settings
from django.db import models


class OrderStatus(models.TextChoices):
    PENDING_PAYMENT = "pending_payment", "Pending payment"
    PAID = "paid", "Paid"
    CANCELLED = "cancelled", "Cancelled"
    REFUNDED = "refunded", "Refunded"


class PaymentMethod(models.TextChoices):
    CARD = "card", "Card"
    CASH = "cash", "Cash"
    FREE = "free", "Free"


class Order(models.Model):
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders"
    )
    status = models.CharField(max_length=20, choices=OrderStatus.choices)
    payment_method = models.CharField(max_length=10, choices=PaymentMethod.choices)
    total_cents = models.IntegerField()
    currency = models.CharField(max_length=3)
    # Staff member who rang it up at the Spit; null when the member bought online.
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "orders"
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"order {self.id} ({self.status})"


class OrderLine(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT)
    price = models.ForeignKey("catalog.Price", on_delete=models.PROTECT)
    # Snapshots, so the receipt reads the same after the catalog changes.
    product_name = models.CharField(max_length=120)
    amount_cents = models.IntegerField()

    class Meta:
        db_table = "order_lines"
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.product_name} {self.amount_cents}"


class Payment(models.Model):
    """One processor notification that was verified, approved or not."""

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="payments")
    processor = models.CharField(max_length=20)
    transaction_id = models.CharField(max_length=64)
    approved = models.BooleanField()
    amount_cents = models.IntegerField()
    raw_notification = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "payments"
        constraints = [
            models.UniqueConstraint(
                fields=["processor", "transaction_id"], name="payments_processor_transaction_key"
            )
        ]

    def __str__(self) -> str:
        return (
            f"{self.processor} {self.transaction_id} {'approved' if self.approved else 'declined'}"
        )
