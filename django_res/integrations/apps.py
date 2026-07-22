from __future__ import annotations

from typing import Any

from django.apps import AppConfig
from django.db import models


def _person_channel_changed(
    sender: type[models.Model],
    instance: Any,
    **_: Any,
) -> None:
    """PersonEmail/PersonPhone edits ride nested endpoints without touching
    Person (`accounts/serializers/contact.py`), so a child save/delete must
    bump the parent's Zoho push itself (GAP-081)."""
    from accounts.models import Person
    from integrations.services.zoho_flow import enqueue_zoho_push

    try:
        person = instance.contact
    except Person.DoesNotExist:
        # Cascade delete mid-flight (parent row already gone) — nothing to push.
        return
    enqueue_zoho_push(person)


def _person_merged_receiver(sender: type[models.Model], **kwargs: Any) -> None:
    """`Person.merge` rewrites FKs via `.update()` (no post_save) — re-push the
    survivor so the CRM record absorbs the folded-in channels (GAP-081). The
    absorbed row's CRM record is an accepted orphan (no delete endpoint)."""
    from integrations.services.zoho_flow import enqueue_zoho_push

    enqueue_zoho_push(kwargs["survivor"])


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

        # --- Zoho Flow outbound push (GAP-081) ---------------------------
        from accounts.models import Person, PersonEmail, PersonPhone
        from accounts.signals import person_merged
        from integrations.services.zoho_flow import register_zoho_flow
        from integrations.services.zoho_payloads import build_person_payload

        register_zoho_flow(Person, kind="contact", build_payload=build_person_payload)
        for child_model in (PersonEmail, PersonPhone):
            label = child_model._meta.label
            models.signals.post_save.connect(
                _person_channel_changed,
                sender=child_model,
                dispatch_uid=f"integrations.zoho_flow:{label}:post_save",
            )
            models.signals.post_delete.connect(
                _person_channel_changed,
                sender=child_model,
                dispatch_uid=f"integrations.zoho_flow:{label}:post_delete",
            )
        person_merged.connect(
            _person_merged_receiver,
            dispatch_uid="integrations.zoho_flow:person_merged",
        )
