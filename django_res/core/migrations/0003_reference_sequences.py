"""Create the six reference-number Postgres sequences up front.

Five of them back a `db_default=reference_db_default(...)` `nextval(...)`
column default emitted into `payments/0001_initial` (payment / refund /
security-deposit references) and `reservations/0001_initial` (enquiry /
damage-claim references). Those columns are created with a `DEFAULT
nextval('<seq>')`, so the sequence MUST exist first — hence this migration is
a hand-added dependency of both app initials (see their `dependencies`).

The sixth, `quotation_number_seq`, is drawn at runtime by
`core.refs.allocate_quotation_number` (not a column default), but is created
here alongside the rest for a single source of truth.

`OWNED BY` (which needs the owning table + column to exist) is attached later
in each app's `*_sequence_ownership` migration. Names mirror the literals in
`core/refs.py` and the models — migrations must not import runtime code.

Idempotent (`IF NOT EXISTS`) and Postgres-only via the vendor guard so the
SQLite-backed unit suite quietly skips it.
"""

from __future__ import annotations

from django.db import migrations

_SEQUENCES = (
    "quotation_number_seq",
    "enquiry_reference_seq",
    "damage_claim_reference_seq",
    "payment_reference_seq",
    "refund_reference_seq",
    "security_deposit_reference_seq",
)


def _forwards(apps, schema_editor) -> None:  # type: ignore[no-untyped-def]
    if schema_editor.connection.vendor != "postgresql":
        return
    for seq in _SEQUENCES:
        schema_editor.execute(f"CREATE SEQUENCE IF NOT EXISTS {seq};")


def _backwards(apps, schema_editor) -> None:  # type: ignore[no-untyped-def]
    if schema_editor.connection.vendor != "postgresql":
        return
    for seq in _SEQUENCES:
        schema_editor.execute(f"DROP SEQUENCE IF EXISTS {seq};")


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_postgres_extensions"),
    ]

    operations = [
        migrations.RunPython(_forwards, _backwards, elidable=False),
    ]
