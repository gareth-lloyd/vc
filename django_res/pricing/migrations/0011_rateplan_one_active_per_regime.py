"""GAP-110 U4: one *active* `RatePlan` per (property, currency, price basis).

The regime bucket is unique: carry-forward now writes periods into the
existing plan (never a new one), so a second active plan in a regime can only
be an operator mistake. Retired (`is_active=False`) plans may pile up; their
periods still own their dates under `rateperiod_no_overlap`.

A DB loaded before the U0 regroup holds one *active* plan per legacy season —
several per (villa, currency) — which the constraint would refuse before the
loader could ever re-run to purge them. `retire_season_keyed_plans` deactivates
those rows first (legacy-keyed by season id rather than `villa:<id>:<CODE>`);
the next `loadlegacy` run deletes them. Audit rule: this is a `RunPython`
`.update()` on a tracked model — historical models carry no signal receivers,
and the migration is its own trail. Any remaining duplicate (hand-built) still
fails loudly: deactivate the extras by hand first.
"""

from __future__ import annotations

from django.db import migrations, models


def retire_season_keyed_plans(apps, schema_editor) -> None:  # type: ignore[no-untyped-def]
    RatePlan = apps.get_model("pricing", "RatePlan")
    RatePlan.objects.filter(is_active=True, legacy_id__isnull=False).exclude(
        legacy_id__startswith="villa:"
    ).update(is_active=False)


class Migration(migrations.Migration):
    dependencies = [
        ("pricing", "0010_rateperiod_regime_exclusion"),
    ]

    operations = [
        migrations.RunPython(retire_season_keyed_plans, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="rateplan",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_active", True)),
                fields=("property", "currency", "price_basis"),
                name="rateplan_one_active_per_regime",
                violation_error_message=(
                    "This property already has an active plan for this currency and price "
                    "basis — add periods to it or carry forward instead."
                ),
            ),
        ),
    ]
