from __future__ import annotations

from django.conf import settings
from django.db import models


class UserSession(models.Model):
    """Denormalised index over django_session, keyed by user.

    Created on login (post_login signal); updated on each request via the
    AuditMiddleware; deleted alongside the Session row on revoke. Listing
    a user's sessions hits this row rather than scanning django_session.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sessions",
    )
    session_key = models.CharField(max_length=40, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    user_agent = models.CharField(max_length=512, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "last_seen_at"]),
        ]
