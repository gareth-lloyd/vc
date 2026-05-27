"""Tests for Quotation transitions and QuotationLine constraints."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from core.exceptions import InvalidTransition
from pricing.models import Currency
from properties.models import Property
from reservations.enums import QuotationStatus
from reservations.models import Guest, Quotation, QuotationLine, TermsVersion


@pytest.fixture
def quotation(db: None, guest: Guest, gbp: Currency, terms: TermsVersion) -> Quotation:
    return Quotation.objects.create(
        guest=guest,
        currency=gbp,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )


@pytest.fixture
def line(quotation: Quotation, property_: Property) -> QuotationLine:
    return QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        adults=2,
        total=Decimal("1400.00"),
    )


@pytest.mark.django_db
def test_quotation_reference_auto_generated(quotation: Quotation) -> None:
    assert quotation.reference.startswith("Q-")


@pytest.mark.django_db
def test_send_draft_to_sent(quotation: Quotation) -> None:
    quotation.send()
    quotation.refresh_from_db()
    assert quotation.status == QuotationStatus.SENT.value


@pytest.mark.django_db
def test_send_on_already_sent_is_idempotent(quotation: Quotation) -> None:
    """Per `08-quotation/transmission.md` "two send paths", `send()` shares the
    post-send helper with the manual-mark endpoint and inherits its idempotency
    short-circuit — re-sending a SENT quote must be a no-op, not a raise."""
    quotation.send()
    quotation.send()  # second send must not raise
    quotation.refresh_from_db()
    assert quotation.status == QuotationStatus.SENT.value


@pytest.mark.django_db
def test_send_from_non_draft_non_sent_state_raises(
    quotation: Quotation,
    line: QuotationLine,
) -> None:
    """Send from a terminal/diverged state (ACCEPTED, etc.) still raises."""
    quotation.send()
    quotation.accept(line)
    with pytest.raises(InvalidTransition):
        quotation.send()


@pytest.mark.django_db
def test_accept_marks_line_selected(quotation: Quotation, line: QuotationLine) -> None:
    quotation.send()
    quotation.accept(line)
    quotation.refresh_from_db()
    line.refresh_from_db()
    assert quotation.status == QuotationStatus.ACCEPTED.value
    assert line.is_selected is True


@pytest.mark.django_db
def test_accept_from_draft_raises(quotation: Quotation, line: QuotationLine) -> None:
    with pytest.raises(InvalidTransition):
        quotation.accept(line)


@pytest.mark.django_db
def test_accept_rejects_foreign_line(
    quotation: Quotation, line: QuotationLine, guest: Guest, gbp: Currency, terms: TermsVersion
) -> None:
    other = Quotation.objects.create(
        guest=guest,
        currency=gbp,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    other.send()
    with pytest.raises(ValueError):
        other.accept(line)


@pytest.mark.django_db
def test_expire_from_sent(quotation: Quotation) -> None:
    quotation.send()
    quotation.expire()
    quotation.refresh_from_db()
    assert quotation.status == QuotationStatus.EXPIRED.value


@pytest.mark.django_db
def test_cancel_with_reason(quotation: Quotation) -> None:
    quotation.cancel("client withdrew")
    quotation.refresh_from_db()
    assert quotation.status == QuotationStatus.CANCELLED.value
    assert quotation.cancel_reason == "client withdrew"


@pytest.mark.django_db
def test_line_date_constraint(quotation: Quotation, property_: Property) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        QuotationLine.objects.create(
            quotation=quotation,
            property=property_,
            date_from=date(2026, 6, 17),
            date_to=date(2026, 6, 10),
            adults=2,
        )


@pytest.mark.django_db
def test_only_one_selected_line_per_quotation(
    quotation: Quotation, property_: Property, line: QuotationLine
) -> None:
    line.is_selected = True
    line.save(update_fields=["is_selected", "updated_at"])
    other = QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 8),
        adults=2,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        other.is_selected = True
        other.save(update_fields=["is_selected", "updated_at"])
