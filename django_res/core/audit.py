"""Registration API for sensitive-field tracking into AuditLog.

Models opt in by calling `core.audit.track(Model, fields=[...], sensitive=[...])`
in their AppConfig.ready(). A pre_save signal handler reads the registry,
loads the prior row, computes the diff, and writes an AuditLog row.
Sensitive fields are recorded as the literal sentinel "[REDACTED]" rather than
the cleartext value.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import structlog
from django.db import models, transaction
from django.db.models.signals import post_delete, pre_save

logger = structlog.get_logger(__name__)

REDACTED = "[REDACTED]"


@dataclass(frozen=True)
class TrackSpec:
    fields: tuple[str, ...]
    sensitive_fields: frozenset[str] = field(default_factory=frozenset)


_registry: dict[type[models.Model], TrackSpec] = {}


def track(
    model: type[models.Model],
    *,
    fields: Iterable[str],
    sensitive: Iterable[str] = (),
) -> None:
    """Register a model's audited fields. Idempotent."""
    spec = TrackSpec(
        fields=tuple(fields),
        sensitive_fields=frozenset(sensitive),
    )
    _registry[model] = spec
    pre_save.connect(_pre_save_handler, sender=model, dispatch_uid=f"audit:{model._meta.label}")
    post_delete.connect(
        _post_delete_handler,
        sender=model,
        dispatch_uid=f"audit-delete:{model._meta.label}",
    )


def get_spec(model: type[models.Model]) -> TrackSpec | None:
    return _registry.get(model)


@transaction.atomic
def scrub_pii(obj: models.Model, fields: Iterable[str]) -> int:
    """Redact cleartext PII from a subject's whole AuditLog trail (GDPR Art. 17).

    Rewrites both sides of every diff pair for the named `fields` to `REDACTED`
    across all AuditLog rows for `(content_type, object_id)` of `obj`. This is
    the standard GDPR carve-out from the table's append-only contract: row
    identity, actor, timestamps, the `__deleted__` tombstone, and *which* fields
    changed all survive — only the cleartext values are tombstoned.

    Call this from erasure flows (anonymize / merge) *after* the model write, so
    the freshly written `[old, sentinel]` (or deletion) row is caught too.
    Returns the number of rows rewritten.
    """
    from django.contrib.contenttypes.models import ContentType

    from core.models import AuditLog

    field_set = frozenset(fields)
    ct = ContentType.objects.get_for_model(obj.__class__)
    rows = AuditLog.objects.select_for_update().filter(content_type=ct, object_id=str(obj.pk))
    scrubbed = 0
    for row in rows:
        changed = False
        diffs = row.field_diffs
        for name in field_set & diffs.keys():
            pair = diffs[name]
            if not isinstance(pair, list):
                continue
            redacted = [None if side in (None, "", b"") else REDACTED for side in pair]
            if redacted != pair:
                diffs[name] = redacted
                changed = True
        if changed:
            row.save(update_fields=["field_diffs"])
            scrubbed += 1
    logger.info(
        "audit.pii_scrubbed",
        model=obj._meta.label,
        object_id=str(obj.pk),
        rows_scrubbed=scrubbed,
    )
    return scrubbed


def _redact(value: Any, is_sensitive: bool) -> Any:
    if is_sensitive and value not in (None, "", b""):
        return REDACTED
    return value


def _pre_save_handler(sender: type[models.Model], instance: models.Model, **_: Any) -> None:
    spec = _registry.get(sender)
    if spec is None:
        return
    from django.contrib.contenttypes.models import ContentType

    from core.models import AuditLog  # local import to avoid cycle
    from core.threadlocal import get_correlation_id, get_current_user

    if instance.pk is None:
        diffs = {
            f: [None, _redact(getattr(instance, f), f in spec.sensitive_fields)]
            for f in spec.fields
        }
    else:
        DoesNotExist = sender._default_manager.model.DoesNotExist  # type: ignore[attr-defined]
        try:
            old = sender._default_manager.get(pk=instance.pk)
        except DoesNotExist:
            return
        diffs = {}
        for f in spec.fields:
            old_val = getattr(old, f)
            new_val = getattr(instance, f)
            if old_val != new_val:
                diffs[f] = [
                    _redact(old_val, f in spec.sensitive_fields),
                    _redact(new_val, f in spec.sensitive_fields),
                ]
    if not diffs:
        return
    AuditLog.objects.create(
        content_type=ContentType.objects.get_for_model(sender),
        object_id=str(instance.pk or ""),
        actor_id=getattr(get_current_user(), "pk", None),
        field_diffs=diffs,
        correlation_id=get_correlation_id(),
    )


def _post_delete_handler(sender: type[models.Model], instance: models.Model, **_: Any) -> None:
    spec = _registry.get(sender)
    if spec is None:
        return
    from django.contrib.contenttypes.models import ContentType

    from core.models import AuditLog
    from core.threadlocal import get_correlation_id, get_current_user

    diffs = {
        f: [_redact(getattr(instance, f), f in spec.sensitive_fields), None] for f in spec.fields
    }
    AuditLog.objects.create(
        content_type=ContentType.objects.get_for_model(sender),
        object_id=str(instance.pk),
        actor_id=getattr(get_current_user(), "pk", None),
        field_diffs={"__deleted__": True, **diffs},
        correlation_id=get_correlation_id(),
    )
