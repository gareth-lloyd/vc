"""GAP-110 U2a: `rateperiod_no_overlap` partitions on the regime key.

The EXCLUDE moves from `(plan, daterange)` to `(property, currency, daterange)`
— at most one plan prices a night in a currency for a property, whatever the
plan. Ungated by `is_active` on the period or the plan: an inactive regime
still owns its dates (hand them over by deleting its periods). The columns
were stamped and made NOT NULL in `0008`/`0009`.

On a populated DB this fails if two plans of one (property, currency) already
overlap — the legacy loader regroups seasons onto one plan per regime
(GAP-110 U0), so a clean cutover load never does; a hand-built DB must be
reconciled first (`reconcile_legacy` night-parity section).
"""

from __future__ import annotations

import django.contrib.postgres.constraints
import django.contrib.postgres.fields.ranges
from django.conf import settings
from django.db import migrations

import core.fields


class Migration(migrations.Migration):
    dependencies = [
        ("pricing", "0009_rateperiod_regime_not_null"),
        ("properties", "0007_description_other_information"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="rateperiod",
            name="rateperiod_no_overlap",
        ),
        migrations.AddConstraint(
            model_name="rateperiod",
            constraint=django.contrib.postgres.constraints.ExclusionConstraint(
                expressions=[
                    ("property", "="),
                    ("currency", "="),
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
