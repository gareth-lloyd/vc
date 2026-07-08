"""Tie the payments reference sequences to their owning columns.

The sequences are created in `core/0003_reference_sequences` (they must
pre-exist the `nextval(...)` column defaults in `payments/0001_initial`).
`OWNED BY` needs the tables + columns, so it is attached here. Ownership makes
dropping the column or table reclaim the sequence automatically.

Postgres-only via the vendor guard; the SQLite unit suite skips it.
"""

from __future__ import annotations

from django.db import migrations

_OWNERSHIP = (
    ("payment_reference_seq", "payments_payment.reference"),
    ("refund_reference_seq", "payments_refund.reference"),
    ("security_deposit_reference_seq", "payments_securitydeposit.reference"),
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
        ("payments", "0002_initial"),
    ]

    operations = [
        migrations.RunPython(_forwards, _backwards, elidable=False),
    ]
