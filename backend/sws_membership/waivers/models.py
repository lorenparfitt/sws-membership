"""Waiver templates, resets and signatures. Nothing here is ever edited after insert."""

from django.conf import settings
from django.db import models


class WaiverTemplate(models.Model):
    version = models.IntegerField(unique=True)
    title = models.CharField(max_length=200)
    body_text = models.TextField()
    # sha256 of body_text, stored so a signature can cite exactly what was agreed.
    document_hash = models.CharField(max_length=64)
    published_at = models.DateTimeField()
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        db_table = "waiver_templates"
        ordering = ["-version"]

    def __str__(self) -> str:
        return f"v{self.version} {self.title}"


class WaiverReset(models.Model):
    """An admin decision that every signature before this moment is stale."""

    reset_at = models.DateTimeField()
    reset_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    reason = models.CharField(max_length=300)

    class Meta:
        db_table = "waiver_resets"
        ordering = ["-reset_at"]

    def __str__(self) -> str:
        return f"{self.reset_at:%Y-%m-%d} {self.reason}"


class WaiverSignature(models.Model):
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="waiver_signatures"
    )
    template = models.ForeignKey(WaiverTemplate, on_delete=models.PROTECT)
    signed_at = models.DateTimeField()
    ip_address = models.CharField(max_length=45)
    signer_name = models.CharField(max_length=200)
    signature_key = models.CharField(max_length=200)
    document_hash = models.CharField(max_length=64)
    guardian_name = models.CharField(max_length=200, null=True, blank=True)
    guardian_signature_key = models.CharField(max_length=200, null=True, blank=True)

    class Meta:
        db_table = "waiver_signatures"

    def __str__(self) -> str:
        return f"{self.signer_name} on v{self.template_id} at {self.signed_at:%Y-%m-%d}"
