"""GAP-089: `PastStay` — a historic stay known only from Nick's spreadsheets.

The "Booking History" sheet carries (name, booking number, villa, destination,
year) and nothing else: no dates, no money, no occupancy, no terms. A real
`Booking` needs all of those, and inventing them would put placeholder stays on
calendars and in finance totals. `PastStay` is the honest minimal record: it
feeds the Customer-360 "Past stays" list and the derived `is_repeat_customer`
flag, and is never scheduled, invoiced, or pushed to Zoho (deferred).

Lifecycle: created only by `import_past_bookers`; `person` is PROTECT (matches
`Booking.person`; a contact DELETE with stays 409s via the shared exception
handler) and `Person.merge` rewrites it through the generic related-objects
loop. `Person.anonymize` leaves these rows in place — they carry no PII.
"""

from __future__ import annotations

from django.db import models

from core.models import TimestampedModel


class PastStay(TimestampedModel):
    person = models.ForeignKey(
        "accounts.Person",
        on_delete=models.PROTECT,
        related_name="past_stays",
    )
    # Sheet "Booking Number" (`BN123`); free text — the legacy numbering is not
    # unique (re-issues, `BN450 / 510`) so it is not a key.
    booking_number = models.CharField(max_length=32, blank=True)
    # Villa name as written in the sheet, kept even when `property` resolves.
    villa_name = models.CharField(max_length=255)
    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="past_stays",
    )
    destination = models.CharField(max_length=255, blank=True)
    year = models.PositiveSmallIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)
    # `sheet-stay-<sha1>` idempotency key for the importer (indexed, not unique).
    legacy_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    class Meta:
        ordering = (models.F("year").desc(nulls_last=True), "booking_number")
        indexes = [models.Index(fields=["person", "year"], name="paststay_person_year_idx")]

    def __str__(self) -> str:
        return f"{self.booking_number or 'stay'} {self.villa_name} {self.year or ''}".strip()
