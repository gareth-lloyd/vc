"""GAP-089: `PastStay` — a historic stay known only from Nick's spreadsheets.

The "Booking History" sheet carries (name, booking number, villa, destination,
year) and nothing else: no dates, no money, no occupancy, no terms. A real
`Booking` needs all of those, and inventing them would put placeholder stays on
calendars and in finance totals. `PastStay` is the honest minimal record: it
feeds the Customer-360 "Past stays" list and the derived `is_repeat_customer`
flag, and is never scheduled, invoiced, or pushed to Zoho (deferred).

GAP-113: legacy `VillaArchiveBookings` re-keyed many of those stays with exact
dates and the amount staff recorded, so `date_from` / `date_to` / `amount` /
`currency` are optional display facts — still not a `Booking`: nothing reads
them for availability or finance. `currency` is null when the legacy row had
none (the amount is shown "as recorded", not converted or guessed).

Lifecycle: created by `import_past_bookers` and `import_archive_stays`
(which also blank-fills the GAP-113 fields); `person` is PROTECT (matches
`Booking.person`; a contact DELETE with stays 409s via the shared exception
handler) and `Person.merge` rewrites it through the generic related-objects
loop. `Person.anonymize` keeps the row (FK integrity; villa / year / booking
number are not personal data) but blanks `notes`, the one free-text column fed
from the sheet row — extend `anonymize` if another free-text column is added.
"""

from __future__ import annotations

from django.db import models
from django.db.models import F, Q

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
    # GAP-113: exact stay dates (both or neither) and the amount as recorded in
    # legacy `VillaArchiveBookings`; `currency` null = legacy recorded none.
    date_from = models.DateField(null=True, blank=True)
    date_to = models.DateField(null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.ForeignKey(
        "pricing.Currency",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    # Importer idempotency key (indexed, not unique): `sheet-stay-<sha1>` from
    # `import_past_bookers`, `archive-stay-<Id>` from `import_archive_stays`.
    legacy_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    class Meta:
        ordering = (
            F("year").desc(nulls_last=True),
            F("date_from").desc(nulls_last=True),
            "booking_number",
        )
        indexes = [models.Index(fields=["person", "year"], name="paststay_person_year_idx")]
        constraints = [
            models.CheckConstraint(
                # Explicit not-nulls: a CHECK passes on NULL, so `date_from <
                # date_to` alone would let a one-sided date through.
                condition=Q(date_from__isnull=True, date_to__isnull=True)
                | Q(date_from__isnull=False, date_to__isnull=False, date_from__lt=F("date_to")),
                name="paststay_date_from_lt_date_to",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.booking_number or 'stay'} {self.villa_name} {self.year or ''}".strip()
