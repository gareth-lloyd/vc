"""GAP-110 U6a (contract): `RatePlan` loses its date envelope.

`effective_from` / `effective_to` were an unvalidated date pair nothing tied to
the plan's periods. Since U3 the engine selects `RatePeriod` rows first and
infers the plan; since U4 projection and carry-forward anchor on a period
year. Nothing reads the envelope any more, so the columns and their index go.

`idempotency_key` (+ `rateplan_idempotency_key_unique_per_property`) was the
retry dedupe for the removed `RatePlan:duplicate` endpoint (U2a); nothing has
written it since. Ordering falls back to `(property, pk)` — the plan is a
date-less regime bucket, so "newest envelope first" no longer means anything.

Schema-only; no data is rewritten.
"""

from __future__ import annotations

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("pricing", "0011_rateplan_one_active_per_regime"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="rateplan",
            options={"ordering": ["property", "pk"]},
        ),
        migrations.RemoveConstraint(
            model_name="rateplan",
            name="rateplan_idempotency_key_unique_per_property",
        ),
        migrations.RemoveIndex(
            model_name="rateplan",
            name="pricing_rat_effecti_1aaf7d_idx",
        ),
        migrations.RemoveField(
            model_name="rateplan",
            name="effective_from",
        ),
        migrations.RemoveField(
            model_name="rateplan",
            name="effective_to",
        ),
        migrations.RemoveField(
            model_name="rateplan",
            name="idempotency_key",
        ),
    ]
