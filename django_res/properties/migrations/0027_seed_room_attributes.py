"""Seed the starter `RoomAttribute` catalog rows (GAP-064).

Uses the live ``properties.room_attribute_catalog.sync_room_attributes``
(the comms ``0003_seed_templates`` pattern) so the starter list has a single
source of truth that later re-invocations (``backfill_room_attrs``) share.
If the RoomAttribute field set ever changes incompatibly, this migration
will need a frozen in-place implementation; until then the live function is
the single source of seed truth. Implication links to ``Feature`` rows stay
NULL here — Features are not migration-seeded, so the candidate lookups only
succeed on a later re-sync.
"""

from __future__ import annotations

from typing import Any

from django.db import migrations


def _forwards(apps: Any, schema_editor: Any) -> None:
    from properties.room_attribute_catalog import sync_room_attributes

    sync_room_attributes(
        model=apps.get_model("properties", "RoomAttribute"),
        feature_model=apps.get_model("properties", "Feature"),
    )


def _backwards(apps: Any, schema_editor: Any) -> None:
    from properties.room_attribute_catalog import starter_slugs

    RoomAttribute = apps.get_model("properties", "RoomAttribute")
    RoomAttributeAssignment = apps.get_model("properties", "RoomAttributeAssignment")
    starters = RoomAttribute.objects.filter(slug__in=starter_slugs())
    # Assignments PROTECT their attribute, and none could have existed before
    # this migration seeded the rows — drop them first so the reverse never
    # trips ProtectedError.
    RoomAttributeAssignment.objects.filter(attribute__in=starters).delete()
    starters.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("properties", "0026_roomattribute_roomattributeassignment_room_access_and_more"),
    ]

    operations = [
        migrations.RunPython(_forwards, _backwards),
    ]
