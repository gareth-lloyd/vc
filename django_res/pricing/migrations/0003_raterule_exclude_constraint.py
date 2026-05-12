"""Postgres-only EXCLUDE constraint on RateRule.

Prevents accidental same-(card, priority) rules with overlapping date ranges
and party-size bands. SQLite is used in local dev / CI tests and has no
EXCLUDE support; the migration is a no-op there. The check + unique
constraints in 0002 still cover the basic invariants on SQLite.
"""

from __future__ import annotations

from django.db import migrations


_FORWARD_SQL_PG = (
    "ALTER TABLE pricing_raterule "
    "ADD CONSTRAINT raterule_no_overlap_same_priority "
    "EXCLUDE USING gist ("
    "card_id WITH =, "
    "daterange(date_from, date_to, '[]') WITH &&, "
    "int4range(min_party, max_party, '[]') WITH &&, "
    "priority WITH ="
    ");"
)

_REVERSE_SQL_PG = (
    "ALTER TABLE pricing_raterule DROP CONSTRAINT IF EXISTS raterule_no_overlap_same_priority;"
)


def _apply_forward(apps, schema_editor) -> None:  # type: ignore[no-untyped-def]
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_FORWARD_SQL_PG)


def _apply_reverse(apps, schema_editor) -> None:  # type: ignore[no-untyped-def]
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_REVERSE_SQL_PG)


class Migration(migrations.Migration):
    dependencies = [
        ("pricing", "0002_initial"),
    ]

    operations = [
        migrations.RunPython(_apply_forward, _apply_reverse, elidable=False),
    ]
