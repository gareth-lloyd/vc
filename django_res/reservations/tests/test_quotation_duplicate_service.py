"""Service tests for `QuotationService.duplicate` (SMELL-009).

The clone walk extracted from `QuotationViewSet.duplicate` plus FG-010
idempotency scoped `(enquiry, idempotency_key)`. Header and line copies are
asserted field-by-field — a vague "counts match" test can't catch a silently
dropped column.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import Person
from pricing.models import Currency
from properties.models import Property
from reservations.enums import QuotationStatus
from reservations.models import BookingHold, Quotation, QuotationLine, TermsVersion
from reservations.services.quotations import QuotationService

pytestmark = pytest.mark.django_db


@pytest.fixture
def agent(db: None) -> Person:
    return Person.objects.create(first_name="Agnes", last_name="Agent")


@pytest.fixture
def source(
    customer: Person,
    agent: Person,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> Quotation:
    """Non-default values on every copyable field; `legacy_id` set explicitly
    (nothing sets it by default, which would mask a copy leak)."""
    quotation = Quotation.objects.create(
        enquiry=customer.enquiries_as_customer.create(),
        person=customer,
        agent=agent,
        is_unbranded=True,
        status=QuotationStatus.SENT,
        expires_at=timezone.now() + timedelta(days=3),
        terms_version=terms,
        legacy_id="legacy-q-1",
    )
    QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        currency=gbp,
        date_from=date(2026, 8, 1),
        date_to=date(2026, 8, 8),
        adults=4,
        children=2,
        pricing_snapshot={"total": "2100.00", "rule": "occ-4"},
        total=Decimal("2100.00"),
        discount=Decimal("100.00"),
        inclusions="Daily maid",
        is_selected=True,
        is_manual=True,
        price_override_reason="matched competitor",
        notes="line notes",
        legacy_id="legacy-ql-1",
    )
    return quotation


def test_clone_copies_header_fields_verbatim(source: Quotation) -> None:
    clone = QuotationService.duplicate(source)

    assert clone.pk != source.pk
    assert clone.enquiry_id == source.enquiry_id
    assert clone.person_id == source.person_id
    assert clone.agent_id == source.agent_id
    assert clone.is_unbranded is True
    assert clone.terms_version_id == source.terms_version_id
    # Deliberately verbatim — a stale expiry clones stale (pinned so the
    # behaviour can't drift silently; changing it is a product call).
    assert clone.expires_at == source.expires_at


def test_clone_is_draft_with_fresh_number_reference_and_no_legacy_id(
    source: Quotation,
) -> None:
    clone = QuotationService.duplicate(source)

    assert clone.status == QuotationStatus.DRAFT
    assert clone.number != source.number
    assert clone.reference != source.reference
    assert clone.legacy_id is None
    assert clone.cancel_reason == ""


def test_clone_copies_lines_field_by_field(source: Quotation) -> None:
    clone = QuotationService.duplicate(source)

    line = clone.lines.get()
    src = source.lines.get()
    assert line.pk != src.pk
    assert line.quotation_id == clone.pk
    assert line.property_id == src.property_id
    assert line.currency_id == src.currency_id
    assert (line.date_from, line.date_to) == (date(2026, 8, 1), date(2026, 8, 8))
    assert (line.adults, line.children) == (4, 2)
    assert line.pricing_snapshot == {"total": "2100.00", "rule": "occ-4"}
    assert line.total == Decimal("2100.00")
    assert line.discount == Decimal("100.00")
    assert line.inclusions == "Daily maid"
    assert line.is_selected is False  # never cloned selected
    assert line.is_manual is True
    assert line.price_override_reason == "matched competitor"
    assert line.notes == "line notes"
    assert line.legacy_id is None


def test_clone_places_no_holds(source: Quotation) -> None:
    QuotationService.duplicate(source)
    assert BookingHold.objects.count() == 0


def test_clone_of_a_clone_works(source: Quotation) -> None:
    first = QuotationService.duplicate(source)
    second = QuotationService.duplicate(first)
    assert second.pk not in {source.pk, first.pk}
    assert second.lines.count() == 1


def test_retry_same_key_returns_original_clone_without_new_rows(
    source: Quotation,
) -> None:
    first = QuotationService.duplicate(source, idempotency_key="k-1")
    counts = (Quotation.objects.count(), QuotationLine.objects.count())

    second = QuotationService.duplicate(source, idempotency_key="k-1")

    assert second.pk == first.pk
    assert (Quotation.objects.count(), QuotationLine.objects.count()) == counts


def test_no_key_creates_a_new_clone_each_time(source: Quotation) -> None:
    first = QuotationService.duplicate(source)
    second = QuotationService.duplicate(source)
    assert first.pk != second.pk
    assert first.idempotency_key == "" == second.idempotency_key


def test_same_key_on_different_enquiries_coexists(
    source: Quotation,
    customer: Person,
    terms: TermsVersion,
) -> None:
    other = Quotation.objects.create(
        enquiry=customer.enquiries_as_customer.create(),
        person=customer,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    assert other.enquiry_id != source.enquiry_id

    first = QuotationService.duplicate(source, idempotency_key="shared")
    second = QuotationService.duplicate(other, idempotency_key="shared")

    assert first.pk != second.pk


def test_db_backstop_rejects_second_row_with_same_enquiry_and_key(
    source: Quotation,
) -> None:
    # FG-010: a racing loser past the pre-check must fail loudly on the
    # partial-unique constraint rather than silently duplicate.
    QuotationService.duplicate(source, idempotency_key="k-race")

    with pytest.raises(IntegrityError), transaction.atomic():
        Quotation.objects.create(
            enquiry=source.enquiry,
            person=source.person,
            expires_at=source.expires_at,
            terms_version=source.terms_version,
            idempotency_key="k-race",
        )
