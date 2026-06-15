"""Integration: Property + property-child audit rows (FG-017).

Pins that a Property rename writes an AuditLog row, and that hard-deleting a
property child (Room / PropertyImage / PropertyNearbyPlace / ChangeOverRule /
PropertyContactAssignment) leaves a `__deleted__` tombstone row — the point of
the second-tier registration is reconstructing who removed an inventory row and
when.
"""

from __future__ import annotations

from typing import cast

import pytest
from django.contrib.contenttypes.models import ContentType

from core.models import AuditLog
from properties import factories
from properties.enums import PropertyStatus
from properties.models import (
    ChangeOverRule,
    Property,
    PropertyNearbyPlace,
    Room,
)


@pytest.mark.django_db
def test_property_rename_writes_audit_row() -> None:
    prop = cast(Property, factories.PropertyFactory(name="Old Villa Name"))

    prop.name = "New Villa Name"
    prop.save(update_fields=["name"])

    ct = ContentType.objects.get_for_model(Property)
    rows = AuditLog.objects.filter(content_type=ct, object_id=str(prop.pk))
    name_rows = [r for r in rows if "name" in r.field_diffs]
    assert name_rows, "expected an AuditLog row capturing the property rename"
    assert name_rows[-1].field_diffs["name"] == ["Old Villa Name", "New Villa Name"]


@pytest.mark.django_db
def test_property_status_change_writes_audit_row() -> None:
    prop = cast(Property, factories.PropertyFactory(status=PropertyStatus.DRAFT.value))

    prop.status = PropertyStatus.ACTIVE.value
    prop.save(update_fields=["status"])

    ct = ContentType.objects.get_for_model(Property)
    rows = AuditLog.objects.filter(content_type=ct, object_id=str(prop.pk))
    status_rows = [r for r in rows if "status" in r.field_diffs]
    assert status_rows[-1].field_diffs["status"] == [
        PropertyStatus.DRAFT.value,
        PropertyStatus.ACTIVE.value,
    ]


@pytest.mark.django_db
def test_room_hard_delete_writes_tombstone_row() -> None:
    room = cast(Room, factories.RoomFactory(name="Master Suite"))
    room_pk = room.pk

    room.delete()

    ct = ContentType.objects.get_for_model(Room)
    rows = AuditLog.objects.filter(content_type=ct, object_id=str(room_pk))
    deleted = [r for r in rows if r.field_diffs.get("__deleted__")]
    assert deleted, "expected a __deleted__ tombstone row for the hard-deleted room"
    assert deleted[-1].field_diffs["name"] == ["Master Suite", None]


@pytest.mark.django_db
def test_nearby_place_hard_delete_writes_tombstone_row() -> None:
    place = cast(PropertyNearbyPlace, factories.PropertyNearbyPlaceFactory(name="Old Town Beach"))
    place_pk = place.pk

    place.delete()

    ct = ContentType.objects.get_for_model(PropertyNearbyPlace)
    rows = AuditLog.objects.filter(content_type=ct, object_id=str(place_pk))
    deleted = [r for r in rows if r.field_diffs.get("__deleted__")]
    assert deleted, "expected a __deleted__ tombstone row for the nearby place"
    assert deleted[-1].field_diffs["name"] == ["Old Town Beach", None]


@pytest.mark.django_db
def test_changeover_rule_hard_delete_writes_tombstone_row() -> None:
    rule = cast(ChangeOverRule, factories.ChangeOverRuleFactory())
    rule_pk = rule.pk

    rule.delete()

    ct = ContentType.objects.get_for_model(ChangeOverRule)
    rows = AuditLog.objects.filter(content_type=ct, object_id=str(rule_pk))
    deleted = [r for r in rows if r.field_diffs.get("__deleted__")]
    assert deleted, "expected a __deleted__ tombstone row for the changeover rule"
