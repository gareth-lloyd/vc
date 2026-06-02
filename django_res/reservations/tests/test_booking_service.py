"""Tests for `BookingService.create_from_quotation_line`.

The full booking creation happy-path is covered indirectly by
`test_api_bookings.py` (accept-quotation flow). This file pins the
service-level idempotency contract: a second call with the same
QuotationLine must return the original Booking, not create a new one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from properties.enums import PrefilledChangeOverDay
from properties.models.settings import PropertySettings
from reservations.enums import BookingGuestRole
from reservations.models import (
    Booking,
    BookingEvent,
    BookingGuest,
)
from reservations.services.bookings import BookingService

if TYPE_CHECKING:
    from reservations.models import QuotationLine, TermsVersion


@pytest.mark.django_db
def test_create_from_quotation_line__is_idempotent(
    quotation_line: QuotationLine,
    terms: TermsVersion,
) -> None:
    """A second call with the same QuotationLine returns the first Booking.

    Webhooks retry and operators double-click. Without idempotency the
    second call would either crash (FK/uniqueness collision) or open a
    duplicate Booking — both worse than the no-op we want.
    """
    first = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)
    second = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)

    assert second.pk == first.pk
    assert Booking.objects.filter(quotation_line=quotation_line).count() == 1
    # The created event was emitted exactly once on the first call;
    # the retry must not append a duplicate event row.
    assert BookingEvent.objects.filter(booking=first).count() == 1


@pytest.mark.django_db
def test_create_from_quotation_line_inherits_line_dates(
    quotation_line: QuotationLine,
    terms: TermsVersion,
) -> None:
    """Confirmation never re-validates changeover (GAP-007): any shift already
    happened at pricing time and was persisted onto the line, so the booking
    inherits the line's dates verbatim — even an off-changeover arrival."""
    PropertySettings.objects.create(
        property=quotation_line.property,
        changeover_day=PrefilledChangeOverDay.SAT.value,
    )
    # quotation_line fixture arrives 2026-06-10 (Wednesday); the line was never
    # repriced, so its dates stand as-is and the booking copies them.
    booking = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)

    assert booking.pk is not None
    assert booking.date_from == quotation_line.date_from
    assert booking.date_to == quotation_line.date_to


@pytest.mark.django_db
def test_create_from_quotation_line__creates_lead_booking_guest(
    quotation_line: QuotationLine,
    terms: TermsVersion,
) -> None:
    """Service must create the LEAD BookingGuest row alongside the Booking.

    Without the LEAD row the partial-unique constraints, the
    LEAD → Booking.guest sync signal, and the `LeadGuestProtectedError`
    pre_delete guard are all inert — the BookingGuest invariants only
    fire when a LEAD row actually exists.
    """
    booking = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)

    leads = BookingGuest.objects.filter(booking=booking, role=BookingGuestRole.LEAD.value)
    assert leads.count() == 1
    assert leads.get().guest_id == quotation_line.quotation.guest_id
    assert booking.guest_id == quotation_line.quotation.guest_id


@pytest.mark.django_db
def test_create_from_quotation_line__lead_creation_is_atomic_with_booking(
    quotation_line: QuotationLine,
    terms: TermsVersion,
) -> None:
    """If the LEAD BookingGuest fails to create, the Booking rolls back too.

    Booking + LEAD must be born together inside the same
    `transaction.atomic()` block, otherwise a half-built Booking with no
    LEAD slips into the DB and the invariants are silently broken.
    """
    real_create = BookingGuest.objects.create

    def explode(*args: object, **kwargs: object) -> BookingGuest:
        if kwargs.get("role") == BookingGuestRole.LEAD.value:
            raise RuntimeError("simulated LEAD insert failure")
        return real_create(*args, **kwargs)

    with patch.object(BookingGuest.objects, "create", side_effect=explode):
        with pytest.raises(RuntimeError, match="simulated LEAD insert failure"):
            BookingService.create_from_quotation_line(quotation_line, terms_version=terms)

    assert not Booking.objects.filter(quotation_line=quotation_line).exists()
    assert not BookingGuest.objects.filter(guest=quotation_line.quotation.guest).exists()


@pytest.mark.django_db
def test_create_from_quotation_line__idempotent_does_not_double_lead(
    quotation_line: QuotationLine,
    terms: TermsVersion,
) -> None:
    """A retry must not append a second LEAD row — the partial-unique
    constraint would forbid it, but the service must short-circuit cleanly."""
    first = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)
    BookingService.create_from_quotation_line(quotation_line, terms_version=terms)

    assert BookingGuest.objects.filter(booking=first, role=BookingGuestRole.LEAD.value).count() == 1
