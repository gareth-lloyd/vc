"""Postgres-only EXCLUDE constraints making the rate grid honest.

- `rateperiod_no_overlap` — periods are date-disjoint per plan.
- `rateband_bands_no_overlap` — bands are party-disjoint per period.

Together every `(night, party)` resolves to exactly one cell. Both mix `=`
and `&&` operators on one gist index, so they need `btree_gist`
(`core/0002_postgres_extensions`). RunPython-gated on vendor so the
SQLite-backed unit suite skips them; the check + unique constraints in the
model `Meta` still cover the basic invariants there.

SQL matches the net live state (`pg_get_constraintdef`) after the historical
RateRule→RateBand rename.
"""

from __future__ import annotations

from django.db import migrations

_FORWARD = (
    "ALTER TABLE pricing_rateperiod ADD CONSTRAINT rateperiod_no_overlap "
    "EXCLUDE USING gist (plan_id WITH =, daterange(date_from, date_to, '[]') WITH &&);",
    "ALTER TABLE pricing_rateband ADD CONSTRAINT rateband_bands_no_overlap "
    "EXCLUDE USING gist (period_id WITH =, int4range(min_party, max_party, '[]') WITH &&);",
)

_REVERSE = (
    "ALTER TABLE pricing_rateband DROP CONSTRAINT IF EXISTS rateband_bands_no_overlap;",
    "ALTER TABLE pricing_rateperiod DROP CONSTRAINT IF EXISTS rateperiod_no_overlap;",
)


def _forwards(apps, schema_editor) -> None:  # type: ignore[no-untyped-def]
    if schema_editor.connection.vendor != "postgresql":
        return
    for sql in _FORWARD:
        schema_editor.execute(sql)


def _backwards(apps, schema_editor) -> None:  # type: ignore[no-untyped-def]
    if schema_editor.connection.vendor != "postgresql":
        return
    for sql in _REVERSE:
        schema_editor.execute(sql)


class Migration(migrations.Migration):
    dependencies = [
        ("pricing", "0002_initial"),
        ("core", "0002_postgres_extensions"),
    ]

    operations = [
        migrations.RunPython(_forwards, _backwards, elidable=False),
    ]
