"""Postgres-only EXCLUDE constraints making double-booking impossible.

- `bookinghold_no_overlap_live` — no two unreleased holds overlap on the same
  property. (The expiry check is delegated to the application sweeper, which
  sets `released_at`; Postgres rejects non-IMMUTABLE `now()` in an index
  predicate.)
- `booking_no_overlap_blocking` — no two *blocking-state* bookings overlap on
  the same property (the net predicate includes `pending_owner_approval`).

Both mix `=` and `&&` on one gist index, so they need `btree_gist`
(`core/0002_postgres_extensions`). RunPython-gated on vendor so the
SQLite-backed unit suite skips them; the check + unique constraints in the
model `Meta` still cover the basic invariants there.

SQL matches the net live state (`pg_get_constraintdef`).
"""

from __future__ import annotations

from django.db import migrations

_FORWARD = (
    "ALTER TABLE reservations_bookinghold "
    "ADD CONSTRAINT bookinghold_no_overlap_live "
    "EXCLUDE USING gist (property_id WITH =, daterange(date_from, date_to, '[)') WITH &&) "
    "WHERE (released_at IS NULL);",
    "ALTER TABLE reservations_booking "
    "ADD CONSTRAINT booking_no_overlap_blocking "
    "EXCLUDE USING gist (property_id WITH =, daterange(date_from, date_to, '[)') WITH &&) "
    "WHERE (status IN ("
    "'pending_owner_approval', 'awaiting_deposit', 'deposit_paid', "
    "'awaiting_balance', 'balance_paid', 'checked_in'));",
)

_REVERSE = (
    "ALTER TABLE reservations_booking DROP CONSTRAINT IF EXISTS booking_no_overlap_blocking;",
    "ALTER TABLE reservations_bookinghold DROP CONSTRAINT IF EXISTS bookinghold_no_overlap_live;",
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
        ("reservations", "0002_sequence_ownership"),
        ("core", "0002_postgres_extensions"),
    ]

    operations = [
        migrations.RunPython(_forwards, _backwards, elidable=False),
    ]
