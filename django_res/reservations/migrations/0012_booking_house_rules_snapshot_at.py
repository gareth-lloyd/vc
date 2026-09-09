"""GAP-094 retro — mark when a house-rules snapshot was actually stamped.

Schema only, deliberately. The `0010` backfill wrote today's rules onto every
already-confirmed booking; those bodies are reconstructions, not what the
guest agreed at confirmation. Leaving `house_rules_snapshot_at` null on them
is the marker: null with a non-empty body = "reconstructed by 0010", and the
contract labels it as such (`Booking.house_rules_reconstructed`). A data
migration inventing a timestamp for those rows would erase exactly the
distinction this column exists to keep. Bookings confirmed from now on are
stamped with a real timestamp by `house_rules_stamp`.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("reservations", "0011_bookingdocument"),
    ]

    operations = [
        migrations.AddField(
            model_name="booking",
            name="house_rules_snapshot_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
