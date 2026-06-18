"""Retrofit the plain `Property.features` auto-M2M into an explicit
`PropertyFeature` through model carrying a per-villa `sort_order` (GAP-022,
legacy `MappingOrder`).

Hand-written, NOT `makemigrations` output: the autodetector would DROP the
existing join table and CREATE a fresh empty one, silently losing every link.
Instead we reuse the existing table (`properties_property_features`) in three
moves:

1. A `SeparateDatabaseAndState` whose ``state_operations`` create the through
   model (mirroring the table's current physical columns: ``id``,
   ``property_id``, ``feature_id``) and re-point the M2M at it, with
   ``database_operations=[]`` so NO DDL runs — the existing rows are untouched.
2. A real `AddField` for ``sort_order`` (this, not the state swap, is where the
   column physically comes from; existing rows default to 0).
3. `AlterModelOptions` to record the through's ordering.

See the row-preservation test in
``properties/tests/test_migration_0017_propertyfeature.py``.
"""

from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("properties", "0016_alter_property_options"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="PropertyFeature",
                    fields=[
                        (
                            "id",
                            models.BigAutoField(
                                auto_created=True,
                                primary_key=True,
                                serialize=False,
                                verbose_name="ID",
                            ),
                        ),
                        (
                            "property",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="+",
                                to="properties.property",
                            ),
                        ),
                        (
                            "feature",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="+",
                                to="properties.feature",
                            ),
                        ),
                    ],
                    options={
                        "db_table": "properties_property_features",
                        "unique_together": {("property", "feature")},
                    },
                ),
                migrations.AlterField(
                    model_name="property",
                    name="features",
                    field=models.ManyToManyField(
                        blank=True,
                        related_name="properties",
                        through="properties.PropertyFeature",
                        to="properties.feature",
                    ),
                ),
            ],
            database_operations=[],
        ),
        migrations.AddField(
            model_name="propertyfeature",
            name="sort_order",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterModelOptions(
            name="propertyfeature",
            options={"ordering": ["sort_order", "id"]},
        ),
    ]
