from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q

from comms.enums import SmtpScope
from core.fields import EncryptedTextField
from core.models.base import AuditedModel


class SmtpProfile(AuditedModel):
    """SMTP credentials for either the system mailer or an individual staff user.

    Personal profiles back the "send as agent" quotation-email pattern: the
    quotation leaves the agent's own mailbox so guest replies land in the
    agent's inbox.
    """

    name = models.CharField(max_length=120)
    scope = models.CharField(max_length=16, choices=SmtpScope.choices)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="smtp_profiles",
    )
    host = models.CharField(max_length=255)
    port = models.PositiveSmallIntegerField()
    username = models.CharField(max_length=255)
    encrypted_password = EncryptedTextField(blank=True, default="")
    use_tls = models.BooleanField(default=True)
    from_email = models.EmailField()
    reply_to = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(scope=SmtpScope.PERSONAL, owner__isnull=False)
                    | Q(scope=SmtpScope.SYSTEM, owner__isnull=True)
                ),
                name="smtp_profile_owner_matches_scope",
            ),
            models.UniqueConstraint(
                fields=["scope"],
                condition=Q(scope=SmtpScope.SYSTEM, is_active=True),
                name="one_active_system_smtp_profile",
            ),
            models.UniqueConstraint(
                fields=["owner"],
                condition=Q(scope=SmtpScope.PERSONAL, is_active=True),
                name="one_active_personal_profile_per_user",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.scope})"
