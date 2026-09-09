"""Generated guest-facing documents for a booking (GAP-094)."""

from __future__ import annotations

from django.conf import settings
from django.db import models

from core.models.base import AuditedModel
from reservations.enums import BookingDocumentKind
from reservations.storage import documents_storage


class BookingDocument(AuditedModel):
    """One generated document (today: the contract PDF) for a booking.

    Every generate writes a **new row** rather than overwriting the last one:
    a contract that has been emailed to a guest is a record of what they were
    sent, so a regenerate after a price correction must not erase it. Newest
    first; the filename carries the pk (not a per-booking count — two
    concurrent generates would collide on a count).

    The file lives in the private `documents` storage alias, outside
    `MEDIA_ROOT` and, in prod/staging, in a private bucket: it carries guest
    PII and must never be URL-served. Downloads stream through the staff API.

    `booking` CASCADEs — a document is derivative of its booking, and the demo
    seeder hard-deletes bookings (`seeding/demo_ical.py`), which PROTECT would
    break. Same call as `DamageClaimPhoto`.
    """

    booking = models.ForeignKey(
        "reservations.Booking",
        on_delete=models.CASCADE,
        related_name="documents",
    )
    kind = models.CharField(max_length=32, choices=BookingDocumentKind.choices)
    file = models.FileField(upload_to="booking_documents/%Y/%m/", storage=documents_storage)
    generated_at = models.DateTimeField(auto_now_add=True)
    # The spec names `generated_by`, and it is what the API exposes. It sits
    # alongside `AuditedModel.created_by` (which the service also sets, and
    # which is what actually PROTECTs a staff account from deletion once they
    # have generated a document); SET_NULL here so this column never becomes a
    # second, redundant deletion barrier. Null on the auto path — no request
    # user generated it.
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    sent_to_guest_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-generated_at", "-id"]

    def __str__(self) -> str:
        return f"{self.kind} #{self.pk} for booking #{self.booking_id}"
