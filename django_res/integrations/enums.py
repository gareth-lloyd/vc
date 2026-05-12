"""TextChoices for the integrations app.

Closed enumerations live here, per `00-conventions.md`. String values keep
queries readable and migrations stable.
"""

from __future__ import annotations

from django.db import models


class SyncProvider(models.TextChoices):
    """External system a `SyncRecord` synchronises with."""

    ZOHO_CRM = "ZOHO_CRM", "Zoho CRM"
    FLYWIRE = "FLYWIRE", "Flywire"
    WORDPRESS_SITE = "WORDPRESS_SITE", "WordPress site"
    LEGACY_DOTNET = "LEGACY_DOTNET", "Legacy .NET"


class SyncDirection(models.TextChoices):
    PUSH = "PUSH", "Push"
    PULL = "PULL", "Pull"
    BIDIRECTIONAL = "BIDIRECTIONAL", "Bidirectional"


class SyncStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    IN_SYNC = "IN_SYNC", "In sync"
    DRIFT = "DRIFT", "Drift"
    ERROR = "ERROR", "Error"
    DISABLED = "DISABLED", "Disabled"


class SyncRunStatus(models.TextChoices):
    RUNNING = "RUNNING", "Running"
    SUCCEEDED = "SUCCEEDED", "Succeeded"
    FAILED = "FAILED", "Failed"
    PARTIAL = "PARTIAL", "Partial"


class SyncIssueKind(models.TextChoices):
    DRIFT = "DRIFT", "Drift"
    CONFLICT = "CONFLICT", "Conflict"
    MISSING_REMOTE = "MISSING_REMOTE", "Missing remote"
    MISSING_LOCAL = "MISSING_LOCAL", "Missing local"
    VALIDATION = "VALIDATION", "Validation"
    TRANSIENT_ERROR = "TRANSIENT_ERROR", "Transient error"


class SyncIssueSeverity(models.TextChoices):
    INFO = "INFO", "Info"
    WARNING = "WARNING", "Warning"
    ERROR = "ERROR", "Error"


class OAuthProvider(models.TextChoices):
    """Providers for which we store OAuth credentials.

    Values intentionally mirror `SyncProvider` strings where they overlap so
    the two enums can be compared without translation.
    """

    ZOHO_CRM = "ZOHO_CRM", "Zoho CRM"


class RunTriggeredBy(models.TextChoices):
    SCHEDULE = "SCHEDULE", "Schedule"
    MANUAL = "MANUAL", "Manual"
    SIGNAL = "SIGNAL", "Signal"
