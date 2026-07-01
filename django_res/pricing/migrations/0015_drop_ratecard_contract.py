"""GAP-056 contract: drop `RateCard`, re-home the honest grid onto periods.

Removes the flattened `RateRule.date_from/date_to` + the `card` FK (and the
`RateCard` model), makes `RateRule.period` non-null, and swaps the transitional
card-scoped overlap EXCLUDE for the two constraints that make the grid honest:

- `rateperiod_no_overlap` — periods are date-disjoint per plan.
- `raterule_bands_no_overlap` — bands are party-disjoint per period.

Together: every `(night, party)` resolves to exactly one cell. Both EXCLUDEs
need `btree_gist` (`core.0004_postgres_extensions`) — an `=` and a range `&&`
on one gist index. Postgres-only (SQLite is a no-op, matching 0003/0010); the
CHECK/model constraints still cover the basics there.

The old `raterule_no_overlap` EXCLUDE is dropped FIRST (it reads `card_id`,
`date_from`, `date_to`), before those columns go.
"""

from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models

_DROP_OLD_OVERLAP = "ALTER TABLE pricing_raterule DROP CONSTRAINT IF EXISTS raterule_no_overlap;"

_ADD_PERIOD_NO_OVERLAP = (
    "ALTER TABLE pricing_rateperiod ADD CONSTRAINT rateperiod_no_overlap "
    "EXCLUDE USING gist (plan_id WITH =, daterange(date_from, date_to, '[]') WITH &&);"
)
_DROP_PERIOD_NO_OVERLAP = (
    "ALTER TABLE pricing_rateperiod DROP CONSTRAINT IF EXISTS rateperiod_no_overlap;"
)
_ADD_BANDS_NO_OVERLAP = (
    "ALTER TABLE pricing_raterule ADD CONSTRAINT raterule_bands_no_overlap "
    "EXCLUDE USING gist (period_id WITH =, int4range(min_party, max_party, '[]') WITH &&);"
)
_DROP_BANDS_NO_OVERLAP = (
    "ALTER TABLE pricing_raterule DROP CONSTRAINT IF EXISTS raterule_bands_no_overlap;"
)


def _drop_old_overlap(apps, schema_editor) -> None:  # type: ignore[no-untyped-def]
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_DROP_OLD_OVERLAP)


def _add_disjoint_excludes(apps, schema_editor) -> None:  # type: ignore[no-untyped-def]
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_ADD_PERIOD_NO_OVERLAP)
    schema_editor.execute(_ADD_BANDS_NO_OVERLAP)


def _drop_disjoint_excludes(apps, schema_editor) -> None:  # type: ignore[no-untyped-def]
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_DROP_BANDS_NO_OVERLAP)
    schema_editor.execute(_DROP_PERIOD_NO_OVERLAP)


class Migration(migrations.Migration):
    dependencies = [
        ("pricing", "0014_discount_drop_card"),
        ("core", "0004_postgres_extensions"),  # btree_gist for the EXCLUDE constraints
    ]

    operations = [
        # 1. Drop the card-scoped overlap EXCLUDE before its columns disappear.
        migrations.RunPython(_drop_old_overlap, migrations.RunPython.noop, elidable=False),
        # 2. Re-home RateRule onto the period: drop the flat date axis + card FK.
        migrations.AlterModelOptions(
            name="raterule",
            options={"ordering": ["period", "min_party"]},
        ),
        migrations.RemoveConstraint(
            model_name="raterule",
            name="raterule_date_from_lte_date_to",
        ),
        migrations.RemoveIndex(
            model_name="raterule",
            name="pricing_rat_card_id_c25d6b_idx",
        ),
        migrations.RemoveField(model_name="raterule", name="card"),
        migrations.RemoveField(model_name="raterule", name="date_from"),
        migrations.RemoveField(model_name="raterule", name="date_to"),
        migrations.AlterField(
            model_name="raterule",
            name="period",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="rules",
                to="pricing.rateperiod",
            ),
        ),
        migrations.AddIndex(
            model_name="raterule",
            index=models.Index(
                fields=["period", "min_party"], name="pricing_rat_period__4b935d_idx"
            ),
        ),
        # 3. The card model is now unreferenced — drop it.
        migrations.DeleteModel(name="RateCard"),
        # 4. Enforce the honest grid: periods disjoint per plan, bands disjoint
        #    per period.
        migrations.RunPython(_add_disjoint_excludes, _drop_disjoint_excludes, elidable=False),
    ]
