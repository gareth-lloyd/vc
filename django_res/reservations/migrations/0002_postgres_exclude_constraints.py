"""Postgres-only EXCLUDE constraints on BookingHold + Booking.

Together they make double-booking impossible at the DB level:

- `bookinghold_no_overlap_live`: no two *live* holds overlap on the same
  property (`released_at IS NULL AND expires_at > now()`).
- `booking_no_overlap_active`: no two *active-state* bookings overlap on
  the same property.

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
    ") WHERE (released_at IS NULL AND expires_at > now());"
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
    ]

    operations = [
        migrations.RunPython(_apply_forward, _apply_reverse, elidable=False),
    ]
