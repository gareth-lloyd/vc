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
