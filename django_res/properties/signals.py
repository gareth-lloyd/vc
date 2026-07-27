from __future__ import annotations

from collections.abc import Callable
from operator import attrgetter
from typing import Any

from django.core.exceptions import ObjectDoesNotExist
from django.db import models, transaction
from django.db.models.fields.files import FieldFile
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from properties.models.capacity import PropertyCapacity
from properties.models.contacts import PropertyContactAssignment
from properties.models.features import Collection, PropertyFeature
from properties.models.images import PropertyImage
from properties.models.location import PropertyLocation
from properties.models.property import Property
from properties.models.rooms import Room, RoomAttributeAssignment, RoomBeds


def _delete_stored_file_after_commit(field_file: FieldFile) -> None:
    """Queue the stored file's deletion for when the transaction commits.

    `post_delete` fires *inside* the deleting transaction; deleting from
    storage there would (a) run S3 HTTP calls while holding the DB connection
    and (b) destroy the object even if the transaction later rolls back,
    leaving a surviving row with a dangling key. Deferring to `on_commit`
    means storage only changes once the row deletion is durable. Storage
    `delete` is a no-op for a missing file (e.g. a legacy key whose binary
    was never imported), so the callback never raises for file-less rows.
    """
    if not field_file:
        return
    storage, name = field_file.storage, field_file.name
    if name is None:
        return
    transaction.on_commit(lambda: storage.delete(name))


@receiver(post_delete, sender=PropertyImage, dispatch_uid="properties.delete_image_file")
def delete_property_image_file(
    sender: type[PropertyImage],
    instance: PropertyImage,
    **kwargs: Any,
) -> None:
    """Release the stored file when a `PropertyImage` row is hard-deleted.

    Rows are hard-deleted (no soft delete), so without this the object would
    leak in storage forever — and S3 bills per stored byte.
    """
    _delete_stored_file_after_commit(instance.image)


@receiver(post_delete, sender=Collection, dispatch_uid="properties.delete_collection_cover")
def delete_collection_cover_file(
    sender: type[Collection],
    instance: Collection,
    **kwargs: Any,
) -> None:
    """Release the stored cover file when a `Collection` row is hard-deleted."""
    _delete_stored_file_after_commit(instance.cover_image)


# ---------------------------------------------------------------------------
# Villa child rows → Zoho villa re-push (GAP-082)
# ---------------------------------------------------------------------------


def _villa_child_zoho_bump(get_property: Callable[[Any], Property]) -> Callable[..., None]:
    """Build a post_save/post_delete receiver that re-pushes the parent villa.

    Child rows ride nested endpoints without touching the Property row, yet
    push inside the villa payload — so a child save/delete must bump the
    parent's Zoho push itself (mirrors `_enquiry_note_zoho_bump`,
    `reservations/signals.py`)."""

    def _handler(sender: type, instance: Any, **_: Any) -> None:
        from integrations.services.zoho_flow import (
            enqueue_zoho_push,
            push_suppressed,
            webhook_url,
        )

        # Guard before the parent deref — bulk cascades under suppression
        # (loaders) or with the webhook unset (dev) shouldn't pay the SELECT.
        if push_suppressed() or not webhook_url("villa"):
            return
        try:
            prop = get_property(instance)
        except ObjectDoesNotExist:
            # Cascade delete mid-flight (a parent row already gone) — the
            # reaper clears the villa's own records.
            return
        enqueue_zoho_push(prop)

    return _handler


_VILLA_CHILDREN: tuple[tuple[type[models.Model], Callable[[Any], Property]], ...] = (
    (PropertyFeature, attrgetter("property")),
    (PropertyContactAssignment, attrgetter("property")),
    (PropertyLocation, attrgetter("property")),
    (PropertyCapacity, attrgetter("property")),
    (Room, attrgetter("property")),
    (PropertyImage, attrgetter("property")),
    # Two hops — either may be mid-cascade, both raises are caught above.
    (RoomBeds, attrgetter("room.property")),
    (RoomAttributeAssignment, attrgetter("room.property")),
)

for _child, _getter in _VILLA_CHILDREN:
    _bump = _villa_child_zoho_bump(_getter)
    # weak=False: the closure has no module-level name, so the default weakref
    # connection would be garbage-collected and silently disconnect.
    post_save.connect(
        _bump,
        sender=_child,
        weak=False,
        dispatch_uid=f"properties.zoho_flow:{_child.__name__}:post_save",
    )
    post_delete.connect(
        _bump,
        sender=_child,
        weak=False,
        dispatch_uid=f"properties.zoho_flow:{_child.__name__}:post_delete",
    )


def _property_features_m2m_zoho_bump(
    sender: type,
    instance: Any,
    action: str,
    reverse: bool,
    **_: Any,
) -> None:
    """`Property.features.set()/.add()` additions ride `bulk_create` on the
    explicit through model — no per-row `post_save` — so m2m_changed is the
    only signal covering them. Removals/clears DO fire per-row `post_delete`
    (connected receivers disable fast-delete, see the audit note in
    properties/apps.py), so those legs double-enqueue harmlessly (PENDING
    dedupe). Production write paths — `_sync_feature_order`, the
    derived-features recompute — are per-row; this covers the manager path
    all the same."""
    if action not in {"post_add", "post_remove", "post_clear"}:
        return
    from integrations.services.zoho_flow import enqueue_zoho_push, push_suppressed, webhook_url

    if push_suppressed() or not webhook_url("villa"):
        return
    if reverse:
        # Feature-side writes (feature.properties.set(...)) don't exist in
        # the codebase; skip rather than bump N villas untested.
        return
    enqueue_zoho_push(instance)


m2m_changed.connect(
    _property_features_m2m_zoho_bump,
    sender=Property.features.through,
    dispatch_uid="properties.zoho_flow:Property.features:m2m_changed",
)
