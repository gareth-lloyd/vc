"""OAuthCredential — encrypted token storage for OAuth integrations.

One active credential per provider at a time (partial unique constraint).
Tokens use `core.fields.EncryptedTextField` (Fernet wrap). See
`08-integrations.md` for the connect/disconnect flow.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.fields import EncryptedTextField
from core.models import AuditedModel
from integrations.enums import OAuthProvider


class OAuthCredential(AuditedModel):
    provider = models.CharField(max_length=32, choices=OAuthProvider.choices)
    account_label = models.CharField(max_length=128, blank=True)

    access_token = EncryptedTextField(blank=True, default="")
    refresh_token = EncryptedTextField(blank=True, default="")
    token_type = models.CharField(max_length=32, default="Bearer")
    expires_at = models.DateTimeField()
    scope = models.CharField(max_length=512, blank=True)
    account_id = models.CharField(max_length=128, blank=True)

    connected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="oauth_connections",
    )
    connected_at = models.DateTimeField(default=timezone.now)
    disconnected_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider"],
                condition=models.Q(is_active=True),
                name="unique_active_oauth_per_provider",
            ),
        ]
        indexes = [
            models.Index(fields=["provider", "is_active"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.provider} ({'active' if self.is_active else 'inactive'})"
