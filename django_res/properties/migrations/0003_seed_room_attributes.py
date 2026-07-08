"""Seed the starter `RoomAttribute` catalog rows (GAP-064).

Uses the live ``properties.room_attribute_catalog.sync_room_attributes`` so
the starter list has a single source of truth that later re-invocations
(``backfill_room_attrs``) share. Implication links to ``Feature`` rows stay
NULL here — Features are not migration-seeded, so candidate lookups only
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
    RoomAttributeAssignment.objects.filter(attribute__in=starters).delete()
    starters.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("properties", "0002_seed_countries"),
    ]

    operations = [
        migrations.RunPython(_forwards, _backwards),
    ]
