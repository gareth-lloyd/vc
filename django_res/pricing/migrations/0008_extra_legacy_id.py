# GAP-107: `Extra.legacy_id` — the legacy `VillaSeasonRate.ID` on catalogue
# rows ported by `ExtraLoader`. Schema only; staff-created extras stay NULL.

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pricing", "0007_extra_idempotency_key_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="extra",
            name="legacy_id",
            field=models.CharField(blank=True, db_index=True, max_length=64, null=True),
        ),
    ]
