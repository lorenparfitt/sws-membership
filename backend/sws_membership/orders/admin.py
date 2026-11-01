"""Django admin for orders: read-only, for looking a sale up."""

from django.contrib import admin

from sws_membership.orders.models import Order, OrderLine, Payment, Refund


class LineInline(admin.TabularInline):
    model = OrderLine
    extra = 0
    can_delete = False
    readonly_fields = ("product", "price", "product_name", "amount_cents")


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    can_delete = False
    readonly_fields = ("processor", "transaction_id", "approved", "amount_cents", "received_at")
    exclude = ("raw_notification",)


class RefundInline(admin.TabularInline):
    model = Refund
    extra = 0
    can_delete = False
    readonly_fields = (
        "payment",
        "amount_cents",
        "processor",
        "transaction_id",
        "reason",
        "refunded_by",
        "refunded_at",
    )
    exclude = ("raw_response",)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "member", "status", "payment_method", "total_cents", "created_at")
    list_filter = ("status", "payment_method")
    search_fields = ("member__last_name", "member__email", "member__member_number")
    readonly_fields = [f.name for f in Order._meta.fields]
    inlines = [LineInline, PaymentInline, RefundInline]
