"""Declarative `register_sync_target` API.

Each domain app's `apps.ready()` registers the models it wants tracked:

    from integrations.signals import register_sync_target
    register_sync_target(Property, providers=["ZOHO_CRM"], direction="PUSH")

The handler reacts to `post_save`:
- On create: writes one `SyncRecord(status=PENDING)` per provider.
- On update: bumps `status=PENDING` only when the registered `fields` (if any)
  actually changed. We compare against the prior row in `pre_save`.

Idempotent: re-registering the same model is a no-op — the handler's
`dispatch_uid` is keyed on model label + provider list.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from django.db import models
from django.db.models.signals import post_save, pre_save

from integrations.enums import SyncDirection, SyncStatus

_FIELD_SNAPSHOT_ATTR = "_integrations_sync_snapshot"


@dataclass(frozen=True)
class SyncTargetSpec:
    providers: tuple[str, ...]
    direction: str
    fields: tuple[str, ...] | None = field(default=None)


_registry: dict[type[models.Model], SyncTargetSpec] = {}


def register_sync_target(
    model: type[models.Model],
    *,
    providers: Iterable[str],
    direction: str = SyncDirection.PUSH.value,
    fields: Iterable[str] | None = None,
) -> None:
    """Register `model` for auto-creation of `SyncRecord` rows.

    `providers` is the list of providers this model syncs to (each gets its
    own SyncRecord). `direction` is the default direction for new records.
    `fields` optionally restricts which field changes mark the record dirty
    (defaults to "any change"); useful so e.g. a typo fix to `notes` doesn't
    flag a Zoho push.

    Idempotent: re-registering the same model overwrites the prior spec and
    the dispatch_uid keeps signal connections deduplicated.
    """
    spec = SyncTargetSpec(
        providers=tuple(providers),
        direction=direction,
        fields=tuple(fields) if fields is not None else None,
    )
    _registry[model] = spec
    pre_save.connect(
        _pre_save_snapshot,
        sender=model,
        dispatch_uid=f"integrations.sync:{model._meta.label}:pre",
    )
    post_save.connect(
        _post_save_handler,
        sender=model,
        dispatch_uid=f"integrations.sync:{model._meta.label}:post",
    )


def unregister_sync_target(model: type[models.Model]) -> None:
    """Remove `model` from the registry and disconnect its signal handlers.

    Used in tests so test-only registrations don't leak across cases.
    """
    _registry.pop(model, None)
    pre_save.disconnect(
        _pre_save_snapshot,
        sender=model,
        dispatch_uid=f"integrations.sync:{model._meta.label}:pre",
    )
    post_save.disconnect(
        _post_save_handler,
        sender=model,
        dispatch_uid=f"integrations.sync:{model._meta.label}:post",
    )


def get_spec(model: type[models.Model]) -> SyncTargetSpec | None:
    return _registry.get(model)


def _pre_save_snapshot(
    sender: type[models.Model],
    instance: models.Model,
    **_: Any,
) -> None:
    """Capture the prior row's tracked field values so post_save can diff."""
    spec = _registry.get(sender)
    if spec is None or spec.fields is None or instance.pk is None:
        return
    try:
        prior = sender._default_manager.get(pk=instance.pk)
    except sender.DoesNotExist:  # type: ignore[attr-defined]
        return
    snapshot = {f: getattr(prior, f) for f in spec.fields}
    setattr(instance, _FIELD_SNAPSHOT_ATTR, snapshot)


def _post_save_handler(
    sender: type[models.Model],
    instance: models.Model,
    created: bool,
    **_: Any,
) -> None:
    spec = _registry.get(sender)
    if spec is None:
        return

    from django.contrib.contenttypes.models import ContentType

    from integrations.models import SyncRecord

    content_type = ContentType.objects.get_for_model(sender)

    if not created and spec.fields is not None:
        snapshot = getattr(instance, _FIELD_SNAPSHOT_ATTR, None)
        if snapshot is not None:
            changed = any(getattr(instance, f) != snapshot.get(f) for f in spec.fields)
            if not changed:
                return

    for provider in spec.providers:
        record, was_created = SyncRecord.objects.get_or_create(
            content_type=content_type,
            object_id=instance.pk,
            provider=provider,
            defaults={
                "direction": spec.direction,
                "status": SyncStatus.PENDING.value,
            },
        )
        if not was_created and record.status != SyncStatus.PENDING.value:
            record.status = SyncStatus.PENDING.value
            record.save(update_fields=["status", "updated_at"])


def _register() -> None:
    """Module-level no-op kept for symmetry with other apps' signals.py."""
