"""Django admin for the catalog: products with their prices, grants and rules inline."""

from django.contrib import admin

from sws_membership.catalog.models import EligibilityRule, EntitlementGrant, Price, Product


class PriceInline(admin.TabularInline):
    model = Price
    extra = 0


class GrantInline(admin.TabularInline):
    model = EntitlementGrant
    extra = 0


class RuleInline(admin.TabularInline):
    model = EligibilityRule
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "season_year", "sort_order", "active")
    list_filter = ("season_year", "active")
    search_fields = ("name",)
    inlines = [PriceInline, GrantInline, RuleInline]
