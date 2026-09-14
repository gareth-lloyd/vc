"""GAP-110 U5a: drop the never-written `PropertyFinance.season` FK.

It pointed a villa's finance record at one `RatePlan` as "the season" — a
legacy-shaped hook nothing ever set (no writer in the API, loaders or seeding;
the only reader was the finance serializer echoing `null`). Under GAP-110 a
plan is a date-less regime bucket, so a single "current season" pointer has no
meaning. Schema-only; no data is rewritten.
"""

from __future__ import annotations

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("properties", "0007_description_other_information"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="propertyfinance",
            name="season",
        ),
    ]
