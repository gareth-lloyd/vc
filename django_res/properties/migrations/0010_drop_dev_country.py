"""Drop the stale 'Dev Country' / legacy_id='25' row left over from the
pre-production schema seed. Safe only if there are no FK references.
"""

from __future__ import annotations

from django.db import migrations


def forwards(apps, schema_editor):
    Country = apps.get_model("properties", "Country")
    stale = Country.objects.filter(legacy_id="25").first()
    if stale is None:
        return

    # Walk reverse relations and bail if anything points at it. Manual
    # cleanup is required before re-running.
    for rel in stale._meta.related_objects:
        if rel.many_to_many:
            continue
        related_model = rel.related_model
        if related_model is None or isinstance(related_model, str):
            continue
        if related_model._default_manager.filter(**{rel.field.name: stale}).exists():
            return

    stale.delete()


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("properties", "0009_seed_iso_3166_countries"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
