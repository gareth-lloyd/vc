from __future__ import annotations

from django.apps import AppConfig


class IntegrationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "integrations"

    def ready(self) -> None:
        from core.audit import track
        from integrations import signals  # noqa: F401
        from integrations.models import OAuthCredential

        # Track sensitive + config-meaningful fields only. Datetime fields
        # (`expires_at`, `disconnected_at`, `connected_at`) are deliberately
        # excluded — the shared `AuditLog.field_diffs` JSONField uses the
        # default JSON encoder, and serialising raw datetimes there would
        # widen `core.audit` semantics. State changes are sufficiently
        # captured via `is_active`.
        track(
            OAuthCredential,
            fields=[
                "provider",
                "account_label",
                "access_token",
                "refresh_token",
                "token_type",
                "scope",
                "account_id",
                "is_active",
            ],
            sensitive=["access_token", "refresh_token"],
        )
