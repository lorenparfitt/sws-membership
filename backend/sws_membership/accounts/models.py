"""Single-use login links. Sessions are Django's own.

Only the hash of a link token is stored. A database leak then exposes
nothing a browser could present, and a token is checked by hashing the
presented value and looking the hash up.
"""

from django.conf import settings
from django.db import models


class LoginToken(models.Model):
    token_hash = models.CharField(max_length=64, unique=True)
    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "login_tokens"
