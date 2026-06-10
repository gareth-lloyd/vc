"""Reference + sequence helpers in core.refs (GAP-006 remediation)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from core.refs import (
    booking_reference,
    next_quotation_number,
    quotation_reference,
    sync_quotation_sequence,
)
from reservations.models import Booking, Guest, Quotation, TermsVersion


def test_quotation_reference_uses_prefix(db: None) -> None:
    assert quotation_reference(1805) == "QVC1805"


@pytest.mark.django_db
def test_booking_reference_plain_when_no_collision() -> None:
    assert booking_reference(1805, model=Booking) == "VC1805"


@pytest.mark.django_db
def test_sync_quotation_sequence_advances_past_imported_max() -> None:
    guest = Guest.objects.create(first_name="Ada", last_name="Lovelace", email="ada@example.com")
    terms = TermsVersion.objects.create(version="2026-01", body_markdown="**T&Cs**")

    # Simulate an import that set `number` explicitly (short-circuiting the
    # sequence draw) to a high value.
    Quotation.objects.create(
        number=5000,
        reference="QVC5000",
        enquiry=guest.enquiries.create(),
        guest=guest,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )

    high_water = sync_quotation_sequence()
    assert high_water == 5000

    # The next organically-allocated number lands above the imported range.
    assert next_quotation_number() == 5001
