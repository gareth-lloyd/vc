"""Postgres-only EXCLUDE constraints on BookingHold + Booking.

Together they make double-booking impossible at the DB level:

- `bookinghold_no_overlap_live`: no two unreleased holds overlap on the same
  property. The original design also gated on `expires_at > now()`, but
  Postgres rejects non-IMMUTABLE functions inside index predicates, so the
  time check is delegated to the application sweeper (which sets
  `released_at` when expiring a hold).
- `booking_no_overlap_active`: no two *active-state* bookings overlap on
  the same property. **Superseded by `booking_no_overlap_blocking` in
  migration 0007**, which also covers `pending_owner_approval`.

The pricing app uses the same RunPython-gated-on-vendor pattern so the
SQLite-backed test suite quietly skips them; check + unique constraints
in 0001 still cover the basic invariants.
"""

from __future__ import annotations

from django.db import migrations


_HOLD_FORWARD_SQL_PG = (
    "ALTER TABLE reservations_bookinghold "
    "ADD CONSTRAINT bookinghold_no_overlap_live "
    "EXCLUDE USING gist ("
    "property_id WITH =, "
    "daterange(date_from, date_to, '[)') WITH &&"
    ") WHERE (released_at IS NULL);"
)

_HOLD_REVERSE_SQL_PG = (
    "ALTER TABLE reservations_bookinghold DROP CONSTRAINT IF EXISTS bookinghold_no_overlap_live;"
)

_BOOKING_FORWARD_SQL_PG = (
    "ALTER TABLE reservations_booking "
    "ADD CONSTRAINT booking_no_overlap_active "
    "EXCLUDE USING gist ("
    "property_id WITH =, "
    "daterange(date_from, date_to, '[)') WITH &&"
    ") WHERE (status IN ("
    "'awaiting_deposit', 'deposit_paid', 'awaiting_balance', "
    "'balance_paid', 'checked_in'"
    "));"
)

_BOOKING_REVERSE_SQL_PG = (
    "ALTER TABLE reservations_booking DROP CONSTRAINT IF EXISTS booking_no_overlap_active;"
)


def _apply_forward(apps, schema_editor) -> None:  # type: ignore[no-untyped-def]
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_HOLD_FORWARD_SQL_PG)
    schema_editor.execute(_BOOKING_FORWARD_SQL_PG)


def _apply_reverse(apps, schema_editor) -> None:  # type: ignore[no-untyped-def]
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_BOOKING_REVERSE_SQL_PG)
    schema_editor.execute(_HOLD_REVERSE_SQL_PG)


class Migration(migrations.Migration):
    dependencies = [
        ("reservations", "0001_initial"),
        ("core", "0004_postgres_extensions"),
    ]

    operations = [
        migrations.RunPython(_apply_forward, _apply_reverse, elidable=False),
    ]
