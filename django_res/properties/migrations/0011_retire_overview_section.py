# Retire `DescriptionSection.OVERVIEW` (2026-09-22).
#
# Its legacy source, `VillaMaster.OverView`, is populated on only 8 of the
# 361 ResProd villas and 6 of those already carry `WebDesc1`, the column
# behind the widely populated `web_des_1`. Folding the two together would be
# lossy for those six and would seed the other two with copy that was never
# the website's top text, so the rows are dropped as an expected loss
# (`data_migration/CUTOVER.md` §6i) rather than remapped — `web_des_1` is
# written from `WebDesc1` only. The `AlterField` carries the choices list
# minus `overview`; `section` stays `max_length=32`.
#
# The bulk `.delete()` bypasses AuditLog on purpose: `PropertyDescription` is
# tracked (`properties/apps.py`), but `core.audit.track` connects its
# receivers with `sender=<concrete model>`, so the historical model here fires
# none — the sanctioned `RunPython` exception in django_res/CLAUDE.md
# §AuditLog. The migration itself is the trail, so each deleted row is logged
# (property, `legacy_id`, body length): a staff-written Overview (legacy_id
# NULL — the tab accepted edits until the SPA change) is gone for good after
# this and the log is the only record of it. (`test_migration_0011` runs
# the callable against the live registry for convenience, so the tombstones
# it observes are an artefact of the test harness, not of a real run.)
#
# Reverse is a no-op: pre-0011 code accepts the narrower choices list as-is
# (Django never validates `choices` on save) and the deleted copy cannot be
# recovered.

from __future__ import annotations

from typing import Any

import structlog
from django.db import migrations, models

logger = structlog.get_logger(__name__)

SECTION_CHOICES = [
    ("house_rules", "House rules"),
    ("web_des_1", "Web des 1"),
    ("web_des_2", "Web des 2"),
    ("interior_sub", "Interior sub"),
    ("interior_para", "Interior para"),
    ("exterior_sub", "Exterior sub"),
    ("exterior_para", "Exterior para"),
    ("location_sub", "Location sub"),
    ("location_para", "Location para"),
    ("internal_notes", "Internal notes"),
    ("other_information", "Other information"),
    ("rooms", "Rooms"),
]


def _forwards(apps: Any, schema_editor: Any) -> None:
    PropertyDescription = apps.get_model("properties", "PropertyDescription")
    rows = PropertyDescription.objects.filter(section="overview")
    for row in rows.iterator():
        logger.warning(
            "properties.overview_description_dropped",
            property_id=row.property_id,
            legacy_id=row.legacy_id,
            body_length=len(row.body or ""),
        )
    rows.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("properties", "0010_description_block_set"),
    ]

    operations = [
        migrations.AlterField(
            model_name="propertydescription",
            name="section",
            field=models.CharField(choices=SECTION_CHOICES, max_length=32),
        ),
        migrations.RunPython(_forwards, migrations.RunPython.noop),
    ]
