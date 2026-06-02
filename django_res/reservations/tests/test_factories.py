"""Factory smoke tests for the reservations app."""

from __future__ import annotations

from typing import cast

import pytest

from reservations import factories, models

pytestmark = pytest.mark.django_db


def test_guest_factory_unique_email() -> None:
    assert factories.GuestFactory().email != factories.GuestFactory().email


def test_enquiry_factory_autogenerates_reference_and_has_guest() -> None:
    enquiry = cast(models.Enquiry, factories.EnquiryFactory())
    assert enquiry.reference  # generated in Enquiry.save()
    assert enquiry.guest_id is not None
    assert enquiry.date_from is not None
    assert enquiry.date_to is not None
    assert enquiry.date_from < enquiry.date_to


def test_terms_version_factory_not_current_by_default() -> None:
    terms = cast(models.TermsVersion, factories.TermsVersionFactory())
    assert terms.is_current is False
    terms.publish()
    assert terms.is_current is True


def test_enquiry_note_factory_persists_with_default_kind() -> None:
    note = cast(models.EnquiryNote, factories.EnquiryNoteFactory())
    assert note.pk is not None
    assert note.enquiry_id is not None
    assert note.body
    assert note.is_pinned is False


def test_booking_note_factory_persists_when_booking_supplied(
    quotation_line: object,
    terms: object,
) -> None:
    """`Booking` is not factoried — caller supplies an instance built via
    `BookingService.create_from_quotation_line`, the production path."""
    from reservations.services.bookings import BookingService

    booking = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)  # type: ignore[arg-type]
    note = cast(
        models.BookingNote,
        factories.BookingNoteFactory(booking=booking),
    )
    assert note.pk is not None
    assert note.booking_id == booking.pk


def test_service_coverage_factory_persists_when_booking_supplied(
    quotation_line: object,
    terms: object,
) -> None:
    from reservations.enums import ServiceStatus
    from reservations.services.bookings import BookingService

    booking = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)  # type: ignore[arg-type]
    coverage = cast(
        models.BookingServiceCoverage,
        factories.BookingServiceCoverageFactory(booking=booking),
    )
    assert coverage.pk is not None
    assert coverage.booking_id == booking.pk
    assert coverage.status == ServiceStatus.NOT_STARTED.value
