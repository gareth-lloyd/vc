"""Zoho Flow outbound push registry + enqueue path (GAP-081).

Thin webhook pusher: res POSTs full-field JSON payloads to per-object-type
Zoho Flow webhook URLs (zapikey-in-URL credential, `settings.ZOHO_FLOW_WEBHOOKS`)
with upsert semantics keyed on res PKs (`RES_ID`). One-way push; `SyncRecord`
is the ops-visible push state.

Deliberately self-contained — this registry does NOT reuse
`integrations.signals.register_sync_target` (that generic machinery stays for
tests/other providers). Each pushed model registers here with its `kind`
(→ webhook URL) and a payload builder; `auto_push=True` connects a `post_save`
handler that enqueues on every save. Models whose push rides an explicit
domain event (e.g. Quotation on send) register `auto_push=False` and call
`enqueue_zoho_push` from their service layer.

`suppress_zoho_push()` makes the whole enqueue path a full no-op (no
`SyncRecord` row, no task dispatch) — `data_migration.BaseLoader` wraps its
row processing in it so `loadlegacy` never avalanches pushes; loaded records
reach Zoho only via the deliberate, throttled backfill.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db import models, transaction

if TYPE_CHECKING:
    from integrations.models import SyncRecord

ZOHO_FLOW_KINDS = ("contact", "enquiry", "quote", "booking")


@dataclass(frozen=True)
class ZohoFlowSpec:
    """How one model pushes to Zoho Flow: which webhook + payload shape."""

    kind: str
    build_payload: Callable[[Any], dict[str, Any]]
    auto_push: bool


_registry: dict[type[models.Model], ZohoFlowSpec] = {}

# Thread-local (Celery prefork workers are processes; runserver threads are
# isolated) suppression flag — see `suppress_zoho_push`.
_suppression = threading.local()


def register_zoho_flow(
    model: type[models.Model],
    *,
    kind: str,
    build_payload: Callable[[Any], dict[str, Any]],
    auto_push: bool = True,
) -> None:
    """Register `model` for Zoho Flow pushes.

    `kind` maps to `settings.ZOHO_FLOW_WEBHOOKS[kind]`. With `auto_push=True`
    a `post_save` handler enqueues a push on every save (dispatch_uid-deduped,
    so re-registering is idempotent). With `auto_push=False` the model only
    pushes when a service calls `enqueue_zoho_push` explicitly.
    """
    if kind not in ZOHO_FLOW_KINDS:
        raise ValueError(f"Unknown Zoho Flow kind {kind!r}; expected one of {ZOHO_FLOW_KINDS}")
    _registry[model] = ZohoFlowSpec(kind=kind, build_payload=build_payload, auto_push=auto_push)
    if auto_push:
        models.signals.post_save.connect(
            _post_save_handler,
            sender=model,
            dispatch_uid=f"integrations.zoho_flow:{model._meta.label}:post_save",
        )
    # Always reap on delete (regardless of auto_push): SyncRecord's GenericFK
    # can't cascade, so deleting a registered target would otherwise orphan
    # its ZOHO_CRM rows (mirrors the FG-007 reaper in integrations.signals).
    models.signals.post_delete.connect(
        _post_delete_reaper,
        sender=model,
        dispatch_uid=f"integrations.zoho_flow:{model._meta.label}:reap",
    )


def unregister_zoho_flow(model: type[models.Model]) -> None:
    """Remove a registration (sacrificial test models ONLY — never the
    `ready()`-registered production models; under xdist that disconnect would
    leak into every other test on the worker)."""
    _registry.pop(model, None)
    models.signals.post_save.disconnect(
        _post_save_handler,
        sender=model,
        dispatch_uid=f"integrations.zoho_flow:{model._meta.label}:post_save",
    )
    models.signals.post_delete.disconnect(
        _post_delete_reaper,
        sender=model,
        dispatch_uid=f"integrations.zoho_flow:{model._meta.label}:reap",
    )


def get_zoho_spec(model: type[models.Model]) -> ZohoFlowSpec | None:
    return _registry.get(model)


def registered_zoho_models() -> dict[type[models.Model], ZohoFlowSpec]:
    """Snapshot of the registry (for the `push_pending` sweep)."""
    return dict(_registry)


def webhook_url(kind: str) -> str:
    """The configured webhook URL for `kind`; `""` = push disabled (dev default)."""
    urls: dict[str, str] = settings.ZOHO_FLOW_WEBHOOKS
    return urls.get(kind, "")


def push_suppressed() -> bool:
    return bool(getattr(_suppression, "active", False))


@contextmanager
def suppress_zoho_push() -> Iterator[None]:
    """Make `enqueue_zoho_push` a full no-op (no SyncRecord row, no dispatch)
    for the duration of the block. Used by `data_migration.BaseLoader`."""
    prior = push_suppressed()
    _suppression.active = True
    try:
        yield
    finally:
        _suppression.active = prior


def is_anonymized_person(instance: models.Model) -> bool:
    """True when `instance` is an `accounts.Person` in ANONYMIZED status.

    ANONYMIZED persons are never pushed (enqueue, sweep-delivery, backfill):
    the row is a PII-scrubbed sentinel kept only for FK integrity.
    """
    from accounts.enums import PersonStatus
    from accounts.models import Person

    return isinstance(instance, Person) and instance.status == PersonStatus.ANONYMIZED


def ensure_pending_record(instance: models.Model) -> SyncRecord:
    """get_or_create/bump the instance's ZOHO_CRM `SyncRecord` to PENDING.

    The record-upsert half of the push pipeline, WITHOUT the skip rules or
    the on_commit dispatch. Shared by `enqueue_zoho_push` (live traffic) and
    the `zoho_backfill` command (deliberate replay — deliberately unaffected
    by `suppress_zoho_push`). Returns the `SyncRecord`.
    """
    from django.contrib.contenttypes.models import ContentType

    from integrations.enums import SyncDirection, SyncProvider, SyncStatus
    from integrations.models import SyncRecord

    content_type = ContentType.objects.get_for_model(instance._meta.model)
    record, was_created = SyncRecord.objects.get_or_create(
        content_type=content_type,
        object_id=instance.pk,
        provider=SyncProvider.ZOHO_CRM.value,
        defaults={
            "direction": SyncDirection.PUSH.value,
            "status": SyncStatus.PENDING.value,
        },
    )
    if not was_created and record.status != SyncStatus.PENDING.value:
        record.status = SyncStatus.PENDING.value
        record.save(update_fields=["status", "updated_at"])
    return record


def enqueue_zoho_push(instance: models.Model) -> None:
    """Mark `instance` PENDING for Zoho Flow push and dispatch on commit.

    get_or_create/bump the `(content_type, object_id, ZOHO_CRM)` `SyncRecord`
    to PENDING, then `push_sync_record.delay` via `transaction.on_commit` so
    the worker never reads a row before its transaction commits.

    Full no-op (no row, no dispatch) when ANY of: suppression is active; the
    model isn't registered; the kind's webhook URL is unset (dev default =
    silently disabled); the instance is an ANONYMIZED Person.
    """
    if push_suppressed():
        return
    spec = _registry.get(instance._meta.model)
    if spec is None:
        return
    if not webhook_url(spec.kind):
        return
    if is_anonymized_person(instance):
        return

    from integrations.tasks import push_sync_record

    record = ensure_pending_record(instance)
    transaction.on_commit(lambda: push_sync_record.delay(record.pk))


def _post_save_handler(
    sender: type[models.Model],
    instance: models.Model,
    **_: Any,
) -> None:
    enqueue_zoho_push(instance)


def _post_delete_reaper(
    sender: type[models.Model],
    instance: models.Model,
    **_: Any,
) -> None:
    """Delete the target's ZOHO_CRM SyncRecords in the same transaction as the
    target (scoped to this provider — other providers' rows are not ours to
    reap). Also mops up the merge case: `Person._merge_channel` deletes child
    rows of the absorbed person, whose post_delete enqueues a PENDING record
    for a person deleted moments later — this removes it with the person row.
    Unconditional (even under suppression): cleanup, not a push."""
    if _registry.get(sender) is None:
        return

    from django.contrib.contenttypes.models import ContentType

    from integrations.enums import SyncProvider
    from integrations.models import SyncRecord

    content_type = ContentType.objects.get_for_model(sender)
    SyncRecord.objects.filter(
        content_type=content_type,
        object_id=instance.pk,
        provider=SyncProvider.ZOHO_CRM.value,
    ).delete()
