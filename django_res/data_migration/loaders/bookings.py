"""Booking + Payment loaders.

VillaBooking has no FK to a QuotationLine — bookings often pre-date the
quotation table or weren't linked. The new Booking schema requires a
quotation_line (PROTECT FK), so for legacy bookings we synthesise a
"legacy-fill" Quotation+Line per booking. Status is set to DRAFT to bypass
the EXCLUDE constraint on active bookings.

Payment: VillaPayment header + VillaPaymentDetails rows -> one Payment row
per detail (purpose=BALANCE by default since legacy doesn't distinguish).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.utils import timezone

from data_migration.base import BaseLoader, LoadReport
from data_migration.loaders.finance import _ensure_default_terms
from payments.enums import PaymentMethod, PaymentPurpose, PaymentStatus
from payments.models.payment import Payment
from pricing.models.currency import Currency
from properties.models.property import Property
from reservations.enums import BookingGuestRole, BookingStatus, QuotationStatus
from reservations.models.booking import Booking
from reservations.models.booking_guest import BookingGuest
from reservations.models.guest import Guest
from reservations.models.quotation import Quotation, QuotationLine


def _decimal(v: Any) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


class BookingLoader(BaseLoader):
    """VillaBooking -> Booking (DRAFT status to bypass EXCLUDE).

    Synthesises a Quotation+QuotationLine per booking since legacy doesn't
    link the two. The synthesised quotation is also DRAFT.
    """

    name = "booking"
    target_model = Booking
    legacy_query = (
        "SELECT Id, VillaId, Guest, FromDate, ToDate, RentalPrice, "
        "DepositAmount, BalanceDue, IsDepositePaid, CurrencyId, "
        "ConciergeNotes, Notes, CreatedAt "
        "FROM VillaBooking WHERE DeletedAt IS NULL"
    )

    def _process_row(self, row: dict[str, Any], report: LoadReport) -> None:
        prop = Property.objects.filter(legacy_id=str(row.get("VillaId") or "")).first()
        guest = Guest.objects.filter(legacy_id=str(row.get("Guest") or "")).first()
        if prop is None or guest is None:
            report.skipped += 1
            return
        currency = None
        if row.get("CurrencyId"):
            currency = Currency.objects.filter(legacy_id=str(row["CurrencyId"])).first()
        if currency is None:
            currency = Currency.objects.first()
        if currency is None:
            report.skipped += 1
            return

        date_from = row.get("FromDate")
        date_to = row.get("ToDate")
        if not (date_from and date_to):
            report.skipped += 1
            return
        if hasattr(date_from, "date"):
            date_from = date_from.date()
        if hasattr(date_to, "date"):
            date_to = date_to.date()
        if date_from >= date_to:
            report.skipped += 1
            return

        terms = _ensure_default_terms()
        booking_legacy = f"booking-{row['Id']}"

        # Synthesise quotation+line per booking (legacy lacks the link).
        quotation, _ = Quotation.objects.update_or_create(
            legacy_id=booking_legacy,
            defaults={
                "guest": guest,
                "currency": currency,
                "expires_at": timezone.now() + timedelta(days=7),
                "status": QuotationStatus.DRAFT,
                "terms_version": terms,
            },
        )
        line, _ = QuotationLine.objects.update_or_create(
            legacy_id=booking_legacy,
            defaults={
                "quotation": quotation,
                "property": prop,
                "date_from": date_from,
                "date_to": date_to,
                "adults": 2,
                "children": 0,
                "total": _decimal(row.get("RentalPrice")) or Decimal("0"),
                "is_manual": True,
            },
        )

        defaults: dict[str, Any] = {
            "quotation_line": line,
            "guest": guest,
            "property": prop,
            "date_from": date_from,
            "date_to": date_to,
            "adults": 2,
            "children": 0,
            "currency": currency,
            "rental_price": _decimal(row.get("RentalPrice")) or Decimal("0"),
            "balance_due": _decimal(row.get("BalanceDue"))
            if isinstance(row.get("BalanceDue"), Decimal)
            else Decimal("0"),
            "status": BookingStatus.DRAFT,
            "terms_version": terms,
            "terms_accepted_at": timezone.now(),
            "payment_method": PaymentMethod.BANK_TRANSFER,
        }
        booking, created = Booking.objects.update_or_create(
            legacy_id=str(row["Id"]),
            defaults=defaults,
        )
        # Loader is idempotent (upsert keyed on legacy_id), so the LEAD row
        # must be too: `get_or_create` on (booking, role=LEAD) reuses the
        # row a previous run already wrote and otherwise births it here so
        # legacy bookings carry the same Booking + LEAD invariant the
        # service-layer path establishes.
        BookingGuest.objects.get_or_create(
            booking=booking,
            role=BookingGuestRole.LEAD.value,
            defaults={"guest": guest},
        )
        if created:
            report.created += 1
        else:
            report.updated += 1


_PAYMENT_STATUS_MAP = {
    "Pending": PaymentStatus.PENDING,
    "Success": PaymentStatus.SUCCEEDED,
    "Succeeded": PaymentStatus.SUCCEEDED,
    "Failed": PaymentStatus.FAILED,
}


class PaymentLoader(BaseLoader):
    """VillaPayment header + VillaPaymentDetails -> Payment rows.

    One Payment per detail; purpose=BALANCE since legacy doesn't separate.
    """

    name = "payment"
    target_model = Payment
    legacy_query = (
        "SELECT d.Id, p.BookingId, d.Amount, d.AmountCurrency, "
        "d.Status, d.PaymentMethod, d.PaymentRefNo "
        "FROM VillaPaymentDetails d "
        "JOIN VillaPayment p ON p.Id = d.PaymentId"
    )

    def transform(self, row: dict[str, Any]) -> dict[str, Any] | None:
        booking = Booking.objects.filter(legacy_id=str(row.get("BookingId") or "")).first()
        if booking is None:
            return None
        currency_code = (row.get("AmountCurrency") or "").strip().upper()
        currency = Currency.objects.filter(code=currency_code).first() or booking.currency

        # The constraint allows one active (PENDING/PROCESSING/SUCCEEDED) row
        # per (booking, BALANCE). Subsequent legacy payment rows become
        # ADJUSTMENT to preserve them without violating the invariant.
        already_has_active_balance = (
            Payment.objects.filter(
                booking=booking,
                purpose=PaymentPurpose.BALANCE,
                status__in=("pending", "processing", "succeeded"),
            )
            .exclude(legacy_id=str(row["Id"]))
            .exists()
        )
        purpose = (
            PaymentPurpose.ADJUSTMENT if already_has_active_balance else PaymentPurpose.BALANCE
        )
        return {
            "booking": booking,
            "purpose": purpose,
            "status": _PAYMENT_STATUS_MAP.get(
                (row.get("Status") or "").strip(),
                PaymentStatus.PENDING,
            ),
            "amount": _decimal(row.get("Amount")) or Decimal("0"),
            "currency": currency,
            "provider_reference": (row.get("PaymentRefNo") or "")[:128],
            "payment_method": PaymentMethod.CARD,
        }
