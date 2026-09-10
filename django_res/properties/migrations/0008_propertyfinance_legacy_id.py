# GAP-107: `PropertyFinance.legacy_id` (rationale on reconcile_legacy's
# PropertyFinance check). Schema only — on a DB loaded before this migration
# every row stays NULL until `loadlegacy property_finance` is re-run
# (data_migration/CUTOVER.md §6f); `reconcile_legacy` reads BLOCKER until then.

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("properties", "0007_description_other_information"),
    ]

    operations = [
        migrations.AddField(
            model_name="propertyfinance",
            name="legacy_id",
            field=models.CharField(blank=True, db_index=True, max_length=64, null=True),
        ),
    ]
