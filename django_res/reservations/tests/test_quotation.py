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
        enquiry=guest.enquiries.create(),
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
    assert quotation.reference.startswith("QVC")


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
        enquiry=guest.enquiries.create(),
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
def test_expire_from_draft(quotation: Quotation) -> None:
    """A DRAFT that ages past `expires_at` can be swept to EXPIRED (SMELL-002)."""
    assert quotation.status == QuotationStatus.DRAFT.value
    quotation.expire()
    quotation.refresh_from_db()
    assert quotation.status == QuotationStatus.EXPIRED.value


@pytest.mark.django_db
def test_expire_from_terminal_raises(quotation: Quotation) -> None:
    """Expiry only applies to live quotations — not already-terminal ones."""
    quotation.cancel("withdrawn")
    with pytest.raises(InvalidTransition):
        quotation.expire()


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
def test_quotation_accept_flips_enquiry_to_converted(
    line: QuotationLine, quotation: Quotation, guest: Guest
) -> None:
    """Accepting a quotation must flip the parent Enquiry to CONVERTED inside
    the same atomic block as the Quotation.status flip."""
    from reservations.enums import EnquiryStatus
    from reservations.models import Enquiry

    enquiry = Enquiry.objects.create(guest=guest, email="ada@example.com")
    quotation.enquiry = enquiry
    quotation.save(update_fields=["enquiry"])
    enquiry.quote_sent(quotation, send_path="smtp")

    quotation.send()
    quotation.accept(line)

    enquiry.refresh_from_db()
    quotation.refresh_from_db()
    assert quotation.status == QuotationStatus.ACCEPTED.value
    assert enquiry.status == EnquiryStatus.CONVERTED.value


@pytest.mark.django_db
def test_quotation_accept_atomic_rollback_on_downstream_failure(
    line: QuotationLine, quotation: Quotation, guest: Guest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the enquiry-conversion step inside accept() fails, the Quotation
    status flip must roll back — the operation is a single atomic unit."""
    from reservations.enums import EnquiryStatus
    from reservations.models import Enquiry

    enquiry = Enquiry.objects.create(guest=guest, email="ada@example.com")
    quotation.enquiry = enquiry
    quotation.save(update_fields=["enquiry"])
    enquiry.quote_sent(quotation, send_path="smtp")
    quotation.send()

    def boom(self: Enquiry, *args: object, **kwargs: object) -> None:
        raise RuntimeError("downstream booking-create-equivalent failure")

    monkeypatch.setattr(Enquiry, "convert", boom)

    with pytest.raises(RuntimeError):
        quotation.accept(line)

    enquiry.refresh_from_db()
    quotation.refresh_from_db()
    line.refresh_from_db()
    # Neither side moved.
    assert quotation.status == QuotationStatus.SENT.value
    assert enquiry.status == EnquiryStatus.QUOTED.value
    assert line.is_selected is False


@pytest.mark.django_db
def test_quotation_accept_without_enquiry_still_works(
    line: QuotationLine, quotation: Quotation
) -> None:
    """Agent-direct quotations have no Enquiry; accept() must still flip status."""
    quotation.send()
    quotation.accept(line)
    quotation.refresh_from_db()
    assert quotation.status == QuotationStatus.ACCEPTED.value


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
