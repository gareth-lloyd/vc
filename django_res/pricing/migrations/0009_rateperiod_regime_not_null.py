"""GAP-110 U1 (contract): `RatePeriod.property` / `.currency` become NOT NULL.

Second half of the expand→contract pair started in `pricing/0008` (which added
the columns nullable and backfilled them); kept separate so the `SET NOT NULL`
never shares a transaction with the backfill UPDATE. Also adds the regime
lookup index the period-first engine (`_load_real_context`) reads.
"""

from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pricing", "0008_rateperiod_property_currency"),
        ("properties", "0007_description_other_information"),
    ]

    operations = [
        migrations.AlterField(
            model_name="rateperiod",
            name="currency",
            field=models.ForeignKey(
                editable=False,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="rate_periods",
                to="pricing.currency",
            ),
        ),
        migrations.AlterField(
            model_name="rateperiod",
            name="property",
            field=models.ForeignKey(
                editable=False,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="rate_periods",
                to="properties.property",
            ),
        ),
        migrations.AddIndex(
            model_name="rateperiod",
            index=models.Index(
                fields=["property", "currency", "date_from", "date_to"],
                name="pricing_rat_propert_771c91_idx",
            ),
        ),
    ]
