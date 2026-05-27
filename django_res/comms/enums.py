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
    # Refused to leave the box — either the recipient was outside the
    # configured allowlist or the dispatch-layer gate was closed. Distinct
    # from FAILED so operators can tell "we wouldn't send" apart from
    # "the SMTP server wouldn't accept".
    BLOCKED = "blocked", "Blocked"
