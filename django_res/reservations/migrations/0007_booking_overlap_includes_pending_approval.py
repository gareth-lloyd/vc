"""Tighten `booking_no_overlap_active` to also block PENDING_OWNER_APPROVAL.

The original exclusion constraint (introduced in 0002) only blocked
overlaps between AWAITING_DEPOSIT and later statuses. Two parallel
quotation-acceptance flows for the same dates could therefore each create
a PENDING_OWNER_APPROVAL booking; the constraint only fired when the
first owner approved, surfacing as an opaque IntegrityError to whoever
lost the race.

Including PENDING_OWNER_APPROVAL means the conflict is detected the
moment the second booking is submitted, and the service layer converts
the IntegrityError into a domain-meaningful `OverlappingBooking`.

The constraint is renamed `booking_no_overlap_blocking` to reflect the
broader semantic ("dates are taken") and avoid masking the rename in
review.
"""

from __future__ import annotations

from django.db import migrations


_DROP_OLD_SQL_PG = (
    "ALTER TABLE reservations_booking DROP CONSTRAINT IF EXISTS booking_no_overlap_active;"
)

_DROP_NEW_SQL_PG = (
    "ALTER TABLE reservations_booking DROP CONSTRAINT IF EXISTS booking_no_overlap_blocking;"
)

_ADD_NEW_SQL_PG = (
    "ALTER TABLE reservations_booking "
    "ADD CONSTRAINT booking_no_overlap_blocking "
    "EXCLUDE USING gist ("
    "property_id WITH =, "
    "daterange(date_from, date_to, '[)') WITH &&"
    ") WHERE (status IN ("
    "'pending_owner_approval', "
    "'awaiting_deposit', 'deposit_paid', 'awaiting_balance', "
    "'balance_paid', 'checked_in'"
    "));"
)

_ADD_OLD_SQL_PG = (
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


# Detect rows that would violate the new (stricter) constraint *before*
# trying to install it. ADD CONSTRAINT … EXCLUDE validates against existing
# data; without this pre-check, the migration aborts mid-deploy with the
# raw psycopg error from inside the constraint validator.
_PRECHECK_SQL_PG = """
SELECT
  a.id AS a_id, a.reference AS a_reference, a.status AS a_status,
  a.date_from AS a_from, a.date_to AS a_to,
  b.id AS b_id, b.reference AS b_reference, b.status AS b_status,
  b.date_from AS b_from, b.date_to AS b_to
FROM reservations_booking a
JOIN reservations_booking b
  ON a.property_id = b.property_id
 AND a.id < b.id
 AND daterange(a.date_from, a.date_to, '[)')
     && daterange(b.date_from, b.date_to, '[)')
WHERE a.status IN (
  'pending_owner_approval', 'awaiting_deposit', 'deposit_paid',
  'awaiting_balance', 'balance_paid', 'checked_in'
)
  AND b.status IN (
  'pending_owner_approval', 'awaiting_deposit', 'deposit_paid',
  'awaiting_balance', 'balance_paid', 'checked_in'
);
"""


def _apply_forward(apps, schema_editor) -> None:  # type: ignore[no-untyped-def]
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(_PRECHECK_SQL_PG)
        conflicts = cursor.fetchall()
    if conflicts:
        sample = "\n".join(
            f"  #{row[0]} ({row[1]}, {row[2]}, {row[3]}..{row[4]}) overlaps "
            f"#{row[5]} ({row[6]}, {row[7]}, {row[8]}..{row[9]})"
            for row in conflicts[:10]
        )
        raise RuntimeError(
            f"Cannot install booking_no_overlap_blocking: {len(conflicts)} pre-existing "
            "overlap(s) found. Resolve manually (cancel the loser, merge bookings, or "
            "adjust dates) before re-running this migration.\n"
            f"First {min(len(conflicts), 10)} overlap(s):\n{sample}"
        )
    schema_editor.execute(_DROP_OLD_SQL_PG)
    schema_editor.execute(_ADD_NEW_SQL_PG)


def _apply_reverse(apps, schema_editor) -> None:  # type: ignore[no-untyped-def]
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_DROP_NEW_SQL_PG)
    schema_editor.execute(_ADD_OLD_SQL_PG)


class Migration(migrations.Migration):
    dependencies = [
        ("reservations", "0006_bookinghold_notes"),
    ]

    operations = [
        migrations.RunPython(_apply_forward, _apply_reverse, elidable=False),
    ]
