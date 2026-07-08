"""Tie the reservations reference sequences to their owning columns.

The sequences themselves are created in `core/0003_reference_sequences`
(they must pre-exist the `nextval(...)` column defaults in
`reservations/0001_initial`). `OWNED BY` needs the tables + columns to exist,
so it is attached here, after the initial. Ownership makes dropping the column
or table reclaim the sequence automatically.

Postgres-only via the vendor guard; the SQLite unit suite skips it.
"""

from __future__ import annotations

from django.db import migrations

_OWNERSHIP = (
    ("quotation_number_seq", "reservations_quotation.number"),
    ("enquiry_reference_seq", "reservations_enquiry.reference"),
    ("damage_claim_reference_seq", "reservations_damageclaim.reference"),
)


def _forwards(apps, schema_editor) -> None:  # type: ignore[no-untyped-def]
    if schema_editor.connection.vendor != "postgresql":
        return
    for seq, column in _OWNERSHIP:
        schema_editor.execute(f"ALTER SEQUENCE {seq} OWNED BY {column};")


def _backwards(apps, schema_editor) -> None:  # type: ignore[no-untyped-def]
    if schema_editor.connection.vendor != "postgresql":
        return
    for seq, _ in _OWNERSHIP:
        schema_editor.execute(f"ALTER SEQUENCE {seq} OWNED BY NONE;")


class Migration(migrations.Migration):
    dependencies = [
        ("reservations", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(_forwards, _backwards, elidable=False),
    ]
