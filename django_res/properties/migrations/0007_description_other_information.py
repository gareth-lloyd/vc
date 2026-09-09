# GAP-091: `villa_info` → `other_information` (+ new `rooms` section).
#
# `section` is widened first: "other_information" is 17 chars and the column
# was 16. The rename is a bulk `.update()` — it bypasses AuditLog on purpose
# (a schema rename, not a user edit; sanctioned in django_res/CLAUDE.md
# §AuditLog). Renamed bodies are still the loader's fused
# FeatureDescription+RoomDescription text, which no string split can undo:
# the property loader re-run in `data_migration/CUTOVER.md` (GAP-091 step)
# rewrites each side into its own section and drops the stale one.

from __future__ import annotations

from typing import Any

from django.db import migrations, models

SECTION_CHOICES = [
    ("overview", "Overview"),
    ("house_rules", "House rules"),
    ("further_info", "Further info"),
    ("location", "Location"),
    ("web_description", "Web description"),
    ("internal_notes", "Internal notes"),
    ("other_information", "Other information"),
    ("rooms", "Rooms"),
]


def _forwards(apps: Any, schema_editor: Any) -> None:
    PropertyDescription = apps.get_model("properties", "PropertyDescription")
    PropertyDescription.objects.filter(section="villa_info").update(section="other_information")


def _backwards(apps: Any, schema_editor: Any) -> None:
    # Any `rooms` rows are left in place on purpose (deleting would lose copy);
    # pre-0007 code 404s that slug until the migration is re-applied.
    PropertyDescription = apps.get_model("properties", "PropertyDescription")
    PropertyDescription.objects.filter(section="other_information").update(section="villa_info")


class Migration(migrations.Migration):
    dependencies = [
        ("properties", "0006_remove_property_category"),
    ]

    operations = [
        migrations.AlterField(
            model_name="propertydescription",
            name="section",
            field=models.CharField(choices=SECTION_CHOICES, max_length=32),
        ),
        migrations.RunPython(_forwards, _backwards),
    ]
