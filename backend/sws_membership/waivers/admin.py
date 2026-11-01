"""Django admin for waivers: read-only history of versions, resets and signatures."""

from django.contrib import admin

from sws_membership.waivers.models import WaiverReset, WaiverSignature, WaiverTemplate


@admin.register(WaiverTemplate)
class WaiverTemplateAdmin(admin.ModelAdmin):
    list_display = ("version", "title", "published_at", "published_by")
    readonly_fields = ("version", "document_hash", "published_at", "published_by")


@admin.register(WaiverReset)
class WaiverResetAdmin(admin.ModelAdmin):
    list_display = ("reset_at", "reason", "reset_by")


@admin.register(WaiverSignature)
class WaiverSignatureAdmin(admin.ModelAdmin):
    list_display = ("member", "template", "signed_at", "signer_name", "guardian_name")
    search_fields = ("member__last_name", "member__email", "signer_name")
    readonly_fields = [f.name for f in WaiverSignature._meta.fields]
