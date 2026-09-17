"""BUG-015 — constraints and index key on `BookingHold.status`.

Split from 0014 so the backfill's data write commits before the CHECK and the
re-created EXCLUDE are validated (Postgres refuses ALTER TABLE on a table with
pending trigger events in the same transaction). Under the new CHECK,
`status = 'live'` is exactly the old `released_at IS NULL`, so the EXCLUDE
covers the same rows as before.

Deploy window (accepted): between `migrate` and the instance swap, old code's
bulk `.update(released_at=...)` release/expire writes violate the CHECK and
500. Old-code inserts still work via the column's `db_default`.
"""

import core.fields
import django.contrib.postgres.constraints
import django.contrib.postgres.fields.ranges
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("properties", "0009_propertyfinance_legacy_id"),
        ("reservations", "0014_bookinghold_status"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="bookinghold",
            name="bookinghold_no_overlap_live",
        ),
        migrations.RemoveIndex(
            model_name="bookinghold",
            name="reservation_propert_cb20a5_idx",
        ),
        migrations.AddIndex(
            model_name="bookinghold",
            index=models.Index(
                fields=["property", "status", "expires_at"], name="reservation_propert_74f09a_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="bookinghold",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("released_at__isnull", True), ("status", "live")),
                    models.Q(
                        models.Q(("status", "live"), _negated=True), ("released_at__isnull", False)
                    ),
                    _connector="OR",
                ),
                name="bookinghold_status_matches_released_at",
            ),
        ),
        migrations.AddConstraint(
            model_name="bookinghold",
            constraint=django.contrib.postgres.constraints.ExclusionConstraint(
                condition=models.Q(("status", "live")),
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
