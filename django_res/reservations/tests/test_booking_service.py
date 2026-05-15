"""Tests for `BookingService.create_from_quotation_line`.

The full booking creation happy-path is covered indirectly by
`test_api_bookings.py` (accept-quotation flow). This file pins the
service-level idempotency contract: a second call with the same
QuotationLine must return the original Booking, not create a new one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from core.exceptions import ChangeoverViolation
from properties.enums import PrefilledChangeOverDay
from properties.models.settings import PropertySettings
from reservations.models import (
    Booking,
    BookingEvent,
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
def test_create_from_quotation_line_enforces_changeover(
    quotation_line: QuotationLine,
    terms: TermsVersion,
) -> None:
    """A quote can pre-date a ChangeOverRule; confirmation re-validates."""
    PropertySettings.objects.create(
        property=quotation_line.property,
        changeover_day=PrefilledChangeOverDay.SAT.value,
    )
    # quotation_line fixture arrives 2026-06-10 (Wednesday).
    with pytest.raises(ChangeoverViolation):
        BookingService.create_from_quotation_line(quotation_line, terms_version=terms)
    assert not Booking.objects.filter(quotation_line=quotation_line).exists()

    booking = BookingService.create_from_quotation_line(
        quotation_line,
        terms_version=terms,
        allow_changeover_override=True,
    )
    assert booking.pk is not None
