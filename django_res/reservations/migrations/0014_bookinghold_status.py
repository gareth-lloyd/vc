"""BUG-015 — `BookingHold.status` (LIVE / RELEASED / EXPIRED).

Until now a hold's lifecycle was `released_at` alone, with expiry and release
indistinguishable once swept. The backfill derives status from
`released_at`/`expires_at` only (never from the new column's own value, so it
is safe to re-run):

- `released_at IS NULL` → live (an expired-but-unswept hold stays live; the
  sweeper expires it on its next tick).
- released at or after its `expires_at` → expired (the sweeper's work).
- any other released row → released.

Known mislabel: an operator release that happened after the hold lapsed but
before the sweep reads EXPIRED. No stored field distinguishes the two, and it
is harmless — the hold was closed either way.

Audit: a `RunPython` backfill on historical models fires no signals, so this
`.update()` writes no AuditLog rows; the migration is the trail (see
django_res/CLAUDE.md, AuditLog registration). The constraints that key on
`status` land in 0015, in their own transaction, after this data write.
"""

from django.db import migrations, models
from django.db.models import F, Q

_LAPSED_BEFORE_RELEASE = Q(expires_at__isnull=False, released_at__gte=F("expires_at"))


def backfill_hold_status(apps, schema_editor):
    BookingHold = apps.get_model("reservations", "BookingHold")
    BookingHold.objects.filter(released_at__isnull=True).update(status="live")
    released = BookingHold.objects.filter(released_at__isnull=False)
    released.filter(_LAPSED_BEFORE_RELEASE).update(status="expired")
    released.exclude(_LAPSED_BEFORE_RELEASE).update(status="released")


class Migration(migrations.Migration):
    dependencies = [
        ("reservations", "0013_paststay_dates_amount"),
    ]

    operations = [
        migrations.AddField(
            model_name="bookinghold",
            name="status",
            field=models.CharField(
                choices=[("live", "Live"), ("released", "Released"), ("expired", "Expired")],
                db_default="live",
                default="live",
                max_length=16,
            ),
        ),
        migrations.RunPython(backfill_hold_status, migrations.RunPython.noop),
    ]
