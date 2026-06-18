"""Give `PropertyFeature.property` a real reverse accessor (`feature_links`)
so the detail serializer can prefetch links ordered by per-villa `sort_order`
(GAP-022 step 4). `related_name` is a Python-side accessor only, so this
`AlterField` emits no SQL."""

from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("properties", "0017_propertyfeature_through"),
    ]

    operations = [
        migrations.AlterField(
            model_name="propertyfeature",
            name="property",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="feature_links",
                to="properties.property",
            ),
        ),
    ]
