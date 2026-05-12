from __future__ import annotations

from django.db import models


class SmtpScope(models.TextChoices):
    SYSTEM = "system", "System"
    PERSONAL = "personal", "Personal"


class EmailLogStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    SENT = "sent", "Sent"
    FAILED = "failed", "Failed"
    BOUNCED = "bounced", "Bounced"
