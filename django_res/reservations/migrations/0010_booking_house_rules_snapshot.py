"""GAP-094 — `Booking.house_rules_snapshot`, stamped at confirmation.

Backfill: bookings that are already confirmed (status at/after
AWAITING_DEPOSIT, or with a transition event into it) get the property's
*current* house rules. There is no history to recover the text as it stood
at the time, so "best available now" is the honest choice; from here on the
transition stamps the snapshot itself. Bounded blast radius: every Booking
row is new-system (legacy history lands in PastStay, not Booking), so the
rows touched here were all confirmed under the new system recently.

Audit: `bulk_update` on a tracked model writes no AuditLog rows — a RunPython
backfill runs on historical models that fire no signals anyway; this
migration is the trail (see django_res/CLAUDE.md, AuditLog registration).
"""

from django.db import migrations, models
from django.db.models import Exists, OuterRef, Q

CONFIRMED_OR_LATER = (
    "awaiting_deposit",
    "deposit_paid",
    "awaiting_balance",
    "balance_paid",
    "checked_in",
    "checked_out",
)


def backfill(apps, schema_editor):
    Booking = apps.get_model("reservations", "Booking")
    BookingEvent = apps.get_model("reservations", "BookingEvent")
    PropertyDescription = apps.get_model("properties", "PropertyDescription")

    confirmed_event = BookingEvent.objects.filter(
        booking_id=OuterRef("pk"), to_status="awaiting_deposit"
    )
    bookings = (
        Booking.objects.filter(house_rules_snapshot="")
        .annotate(was_confirmed=Exists(confirmed_event))
        .filter(Q(status__in=CONFIRMED_OR_LATER) | Q(was_confirmed=True))
    )
    rules_by_property = dict(
        PropertyDescription.objects.filter(section="house_rules")
        .exclude(body="")
        .values_list("property_id", "body")
    )
    to_update = []
    for booking in bookings.only("id", "property_id").iterator():
        body = rules_by_property.get(booking.property_id)
        if body:
            booking.house_rules_snapshot = body
            to_update.append(booking)
    Booking.objects.bulk_update(to_update, ["house_rules_snapshot"], batch_size=500)


class Migration(migrations.Migration):
    dependencies = [
        ("reservations", "0009_paststay"),
    ]

    operations = [
        migrations.AddField(
            model_name="booking",
            name="house_rules_snapshot",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
