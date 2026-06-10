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

from core.refs import booking_reference
from data_migration.base import BaseLoader, LoadReport
from data_migration.loaders._util import ensure_enquiry, legacy_quotation_no
from data_migration.loaders.finance import _ensure_default_terms
from payments.enums import PaymentMethod, PaymentPurpose, PaymentStatus
from payments.models.payment import Payment
from pricing.models.currency import Currency
from pricing.services.currency import resolve_property_currency
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
        "DepositAmount, BalanceDue, IsDepositePaid, CurrencyId, QuotationNo, "
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
            # Canonical chain: the villa's rate plans → settings → EUR —
            # never the ordering-dependent `.first()` (GAP-014 step 0).
            currency = resolve_property_currency(prop)
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

        # The synthesised quotation is an internal artifact (hidden from public
        # APIs via the `booking-` legacy_id prefix) and must NOT claim the
        # legacy QuotationNo as its `number`: the real QuotationLoader already
        # owns that number on the originating `QVC{QuotationNo}` quotation, and
        # `number`/`reference` are unique. So we leave `number` NULL and pin a
        # deterministic per-booking sentinel reference instead. The legacy
        # number is carried forward on the *booking* reference below.
        enquiry = ensure_enquiry(guest, legacy_id=booking_legacy)
        quotation, _ = Quotation.objects.update_or_create(
            legacy_id=booking_legacy,
            defaults={
                "enquiry": enquiry,
                "guest": guest,
                "reference": f"QVC-TMP-{row['Id']}"[:32],
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
                "currency": currency,
                "date_from": date_from,
                "date_to": date_to,
                "adults": 2,
                "children": 0,
                "total": _decimal(row.get("RentalPrice")) or Decimal("0"),
                "is_manual": True,
            },
        )

        # Legacy `VillaBooking.BalanceDue` is a DATETIME — the date the
        # balance falls due — not money (VillaBooking.cs). It feeds
        # `balance_due_at`; the rebuild's `balance_due` is the denormalised
        # guest-facing gross total (07-payments.md), which for legacy rows is
        # the RentalPrice.
        balance_due_at = row.get("BalanceDue")
        if balance_due_at is not None and hasattr(balance_due_at, "date"):
            balance_due_at = balance_due_at.date()

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
            "balance_due": _decimal(row.get("RentalPrice")) or Decimal("0"),
            "balance_due_at": balance_due_at,
            "status": BookingStatus.DRAFT,
            "terms_version": terms,
            "terms_accepted_at": timezone.now(),
            "payment_method": PaymentMethod.BANK_TRANSFER,
        }
        # Carry the legacy QuotationNo forward as the customer-facing
        # `VC{QuotationNo}` (legacy parity), set explicitly because the
        # synthesised quotation deliberately has no `number` to derive from.
        # Only stamp the reference when *creating* the row: re-runs must not
        # rewrite an existing reference (idempotency), and a second legacy
        # booking sharing the QuotationNo is preserved with a `VC{n}-…` suffix
        # rather than colliding. Absent QuotationNo → omit, so Booking.save()
        # falls to its `VC-TMP-…` sentinel rather than a bare `VC{int}`.
        qn = legacy_quotation_no(row)
        existing = Booking.objects.filter(legacy_id=str(row["Id"])).first()
        if existing is None and qn is not None:
            defaults["reference"] = booking_reference(qn, model=Booking)
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
