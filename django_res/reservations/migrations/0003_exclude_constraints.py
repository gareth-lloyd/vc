"""btree_gist EXCLUDE constraints making double-booking impossible (SMELL-022).

- `bookinghold_no_overlap_live` — no two unreleased holds overlap on the same
  property. (The expiry check is delegated to the application sweeper, which
  sets `released_at`; Postgres rejects non-IMMUTABLE `now()` in an index
  predicate.)
- `booking_no_overlap_blocking` — no two *blocking-state* bookings overlap on
  the same property (the predicate includes `pending_owner_approval`).

Both mix `=` and `&&` on one gist index, so they need `btree_gist`
(`core/0002_postgres_extensions`).

Historically these were raw `ALTER TABLE … ADD CONSTRAINT … EXCLUDE` RunPython
SQL; rewritten as `AddConstraint` so the model `Meta` owns them and the
autodetector tracks them (SMELL-022). Environments that applied the RunPython
version keep their `django_migrations` record and identical net schema —
Postgres normalises both routes to the same `pg_get_constraintdef`.

Operations pasted verbatim from `makemigrations` output — do not hand-edit
(deconstruct() mismatches leave `makemigrations --check` permanently dirty).
The status literals are deliberately frozen by value: a future edit to
`OVERLAP_BLOCKING_BOOKING_STATUSES` will surface as a constraint diff.
"""

import core.fields
import django.contrib.postgres.constraints
import django.contrib.postgres.fields.ranges
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("reservations", "0002_sequence_ownership"),
        ("core", "0002_postgres_extensions"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="booking",
            constraint=django.contrib.postgres.constraints.ExclusionConstraint(
                condition=models.Q(
                    (
                        "status__in",
                        (
                            "pending_owner_approval",
                            "awaiting_deposit",
                            "deposit_paid",
                            "awaiting_balance",
                            "balance_paid",
                            "checked_in",
                        ),
                    )
                ),
                expressions=[
                    ("property", "="),
                    (
                        core.fields.DateRangeFunc(
                            "date_from",
                            "date_to",
                            django.contrib.postgres.fields.ranges.RangeBoundary(),
                        ),
                        "&&",
                    ),
                ],
                name="booking_no_overlap_blocking",
            ),
        ),
        migrations.AddConstraint(
            model_name="bookinghold",
            constraint=django.contrib.postgres.constraints.ExclusionConstraint(
                condition=models.Q(("released_at__isnull", True)),
                expressions=[
                    ("property", "="),
                    (
                        core.fields.DateRangeFunc(
                            "date_from",
                            "date_to",
                            django.contrib.postgres.fields.ranges.RangeBoundary(),
                        ),
                        "&&",
                    ),
                ],
                name="bookinghold_no_overlap_live",
            ),
        ),
    ]
