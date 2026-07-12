"""btree_gist EXCLUDE constraints making the rate grid honest (SMELL-022).

- `rateperiod_no_overlap` — periods are date-disjoint per plan.
- `rateband_bands_no_overlap` — bands are party-disjoint per period.

Together every `(night, party)` resolves to exactly one cell. Both mix `=`
and `&&` operators on one gist index, so they need `btree_gist`
(`core/0002_postgres_extensions`).

Historically these were raw `ALTER TABLE … ADD CONSTRAINT … EXCLUDE` RunPython
SQL; rewritten as `AddConstraint` so the model `Meta` owns them and the
autodetector tracks them (SMELL-022). Environments that applied the RunPython
version keep their `django_migrations` record and identical net schema —
Postgres normalises both routes to the same `pg_get_constraintdef`.

Operations pasted verbatim from `makemigrations` output — do not hand-edit
(deconstruct() mismatches leave `makemigrations --check` permanently dirty).
"""

import core.fields
import django.contrib.postgres.constraints
import django.contrib.postgres.fields.ranges
from django.conf import settings
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("pricing", "0002_initial"),
        ("core", "0002_postgres_extensions"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="rateband",
            constraint=django.contrib.postgres.constraints.ExclusionConstraint(
                expressions=[
                    ("period", "="),
                    (
                        core.fields.Int4RangeFunc(
                            "min_party",
                            "max_party",
                            django.contrib.postgres.fields.ranges.RangeBoundary(
                                inclusive_lower=True, inclusive_upper=True
                            ),
                        ),
                        "&&",
                    ),
                ],
                name="rateband_bands_no_overlap",
            ),
        ),
        migrations.AddConstraint(
            model_name="rateperiod",
            constraint=django.contrib.postgres.constraints.ExclusionConstraint(
                expressions=[
                    ("plan", "="),
                    (
                        core.fields.DateRangeFunc(
                            "date_from",
                            "date_to",
                            django.contrib.postgres.fields.ranges.RangeBoundary(
                                inclusive_lower=True, inclusive_upper=True
                            ),
                        ),
                        "&&",
                    ),
                ],
                name="rateperiod_no_overlap",
            ),
        ),
    ]
