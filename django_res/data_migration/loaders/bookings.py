"""Booking + Payment + charge-line loaders.

VillaBooking has no FK to a QuotationLine — bookings often pre-date the
quotation table or weren't linked. The new Booking schema requires a
quotation_line (PROTECT FK), so for legacy bookings we synthesise a
"legacy-fill" Quotation+Line per booking. Status is set to DRAFT to bypass
the EXCLUDE constraint on active bookings.

Payment: VillaPayment header + VillaPaymentDetails rows -> one Payment row
per detail (purpose=BALANCE by default since legacy doesn't distinguish).

BookingChargeItem: VillaBookingDetails rows -> signed charge lines (GAP-017),
loaded with the booking_total_changed payment resync suppressed — see
`_suppress_schedule_resync`.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal
from typing import Any

import structlog
from django.utils import timezone

from core.exceptions import NoRateAvailable
from core.refs import booking_reference
from data_migration.base import BaseLoader, LoadReport
from data_migration.loaders._util import ensure_enquiry, legacy_quotation_no, person_for_client
from data_migration.loaders.finance import _ensure_default_terms
from payments.enums import PaymentMethod, PaymentPurpose, PaymentStatus
from payments.models.payment import Payment
from pricing.models.currency import Currency
from pricing.services.currency import FxConverter, quantise_money, resolve_property_currency
from properties.models.property import Property
from reservations.enums import BookingGuestRole, BookingStatus, QuotationStatus
from reservations.models.booking import Booking
from reservations.models.booking_guest import BookingGuest
from reservations.models.charge_item import BookingChargeItem
from reservations.models.quotation import Quotation, QuotationLine

logger = structlog.get_logger(__name__)


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
        person = person_for_client(row.get("Guest"))
        if prop is None or person is None:
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
        # GAP-045 D5-3: `person` (resolved from the legacy client id via
        # `person_for_client`) is the sole customer FK the loader writes onto the
        # synthesised Quotation / Booking / LEAD BookingGuest and the back-created
        # enquiry. No `Guest` is touched.

        # The synthesised quotation is an internal artifact (hidden from public
        # APIs via the `booking-` legacy_id prefix) and must NOT claim the
        # legacy QuotationNo as its `number`: the real QuotationLoader already
        # owns that number on the originating `QVC{QuotationNo}` quotation, and
        # `number`/`reference` are unique. So we leave `number` NULL and pin a
        # deterministic per-booking sentinel reference instead. The legacy
        # number is carried forward on the *booking* reference below.
        enquiry = ensure_enquiry(person, legacy_id=booking_legacy)
        quotation, _ = Quotation.objects.update_or_create(
            legacy_id=booking_legacy,
            defaults={
                "enquiry": enquiry,
                "person": person,
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
            "person": person,
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
            defaults={"person": person},
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


# payments' registration uid for its booking_total_changed receiver
# (payments/signals.py `_register`). If payments ever renames it the
# suppression tests fail behaviourally (the mocked resync gets called).
_RESYNC_UID = "payments.resync_on_booking_total_changed"


@contextmanager
def _suppress_schedule_resync() -> Iterator[None]:
    """Disconnect the payments booking_total_changed receiver for a load.

    Charge-item writes fire `booking_total_changed` at the model layer, and
    the payments receiver resizes PENDING DEPOSIT/BALANCE schedule rows —
    which imported bookings hold (PaymentLoader defaults unknown legacy
    statuses to PENDING). Loading historical charge lines must not rewrite
    that legacy money, so the one receiver (it drives both the schedule
    resync and the security-deposit resize) is disconnected by its
    dispatch_uid, and reconnected on exit only if this invocation actually
    disconnected it — nesting and deliberate prior disconnects both survive.

    The disconnect is process-global (Django signals are singletons): any
    other charge-item write in the same process during the window also skips
    the resync. Fine for the single-writer `loadlegacy` management command
    this exists for; don't use it in a process serving live traffic.
    """
    from payments.signals import _resync_schedule_on_booking_total_changed
    from reservations.signals import booking_total_changed

    was_connected = booking_total_changed.disconnect(dispatch_uid=_RESYNC_UID)
    try:
        yield
    finally:
        if was_connected:
            booking_total_changed.connect(
                _resync_schedule_on_booking_total_changed,
                dispatch_uid=_RESYNC_UID,
            )


class BookingChargeItemLoader(BaseLoader):
    """VillaBookingDetails -> BookingChargeItem (GAP-017).

    Legacy rows are staff-entered "Chargeable Extras": customer-facing signed
    money lines summed on top of RentalPrice — the same shape as the new
    `balance_due + Σ charge_items`, so same-currency lines port verbatim and
    totals reproduce legacy by construction.

    Currency policy: lines are pinned to `booking.currency` (the Σ in the API
    assumes single-currency rows). CurrencyId=0 means "no currency" in legacy
    (rows were summed blind into the booking total) and pins to the booking
    currency; a non-zero CurrencyId that doesn't resolve raises. A row whose
    currency genuinely differs is never written verbatim: it converts via
    `FxConverter` at the rate pinned to `booking.date_from` (rate + as-of
    provenance kept in `notes`), raises `NoRateAvailable` into `report.errors`
    for manual review when no rate is seeded, or — when the conversion rounds
    to zero — is skipped and any previously loaded line for the row dropped.
    """

    name = "booking_charge_item"
    target_model = BookingChargeItem
    legacy_query = "SELECT Id, BookingId, CurrencyId, Price, Notes FROM VillaBookingDetails"

    def _apply_since(self, query: str) -> str:
        # Deliberate no-op: VillaBookingDetails has no UpdatedAt column, and
        # the removal sweep in `_load_rows` needs the full row set anyway.
        if self.since:
            logger.warning(
                "data_migration.charge_item_since_ignored",
                since=str(self.since),
                reason="VillaBookingDetails has no UpdatedAt; full reload",
            )
        return query

    def _load_rows(self, rows: list[dict[str, Any]], report: LoadReport) -> None:
        with _suppress_schedule_resync():
            super()._load_rows(rows, report)
            # Legacy hard-deletes "Chargeable Extras" (the table has no
            # DeletedAt) and every run reads the full table, so rows that
            # vanished from legacy must vanish here too or a deleted money
            # line keeps inflating the guest total. Staff-created rows
            # (legacy_id NULL) are out of scope; skipped/errored rows keep
            # their ids in `seen`, so a previously-loaded version survives a
            # transient transform failure. Inside the suppression window:
            # post_delete also fires booking_total_changed.
            seen = {str(r["Id"]) for r in rows if r.get("Id") is not None}
            removed, _ = (
                BookingChargeItem.objects.filter(legacy_id__isnull=False)
                .exclude(legacy_id__in=seen)
                .delete()
            )
            if removed:
                logger.info("data_migration.charge_item_rows_removed", count=removed)

    @staticmethod
    def _drop_stale(row: dict[str, Any]) -> None:
        """A zero outcome can follow a previously-loaded nonzero line (legacy
        Price edited to zero, or a corrected FxRate now rounding to zero) —
        drop the stale row so re-runs converge instead of leaving old money
        live. The removal sweep can't do it: skipped rows keep their id in
        its `seen` set."""
        BookingChargeItem.objects.filter(legacy_id=str(row["Id"])).delete()

    def transform(self, row: dict[str, Any]) -> dict[str, Any] | None:
        booking = Booking.objects.filter(legacy_id=str(row.get("BookingId") or "")).first()
        if booking is None:
            return None
        amount = _decimal(row.get("Price"))
        if amount is None:
            # Corrupt money must surface in `report.errors`, not vanish into
            # the skipped count like a legitimate zero.
            raise ValueError(f"unparseable Price {row.get('Price')!r}")
        if amount == 0:
            # amount=0 would violate `bookingchargeitem_amount_nonzero`.
            self._drop_stale(row)
            return None

        row_currency = None
        if row.get("CurrencyId"):
            row_currency = Currency.objects.filter(legacy_id=str(row["CurrencyId"])).first()
            if row_currency is None:
                # Could be a genuinely foreign currency whose legacy row never
                # loaded — writing the amount verbatim is the money bug this
                # loader exists to avoid. (CurrencyId=0 means "no currency"
                # and pins to the booking currency above.)
                raise ValueError(f"unresolvable CurrencyId {row['CurrencyId']}")

        provenance = ""
        if row_currency is not None and row_currency.pk != booking.currency_id:
            # Legacy summed mixed-currency rows blind into the booking total —
            # a latent bug the single-currency Σ contract forbids reproducing.
            # Convert at the most recent rate ≤ date_from (pinned so re-runs
            # are deterministic); no rate → raise into `report.errors` for
            # manual review (ops seeds the FxRate and re-runs).
            original = amount
            fx_ctx = {
                "booking_id": booking.pk,
                "charge_item_legacy_id": str(row.get("Id")),
                "amount": str(original),
                "currency": row_currency.code,
            }
            try:
                rate = FxConverter.lookup_rate(
                    row_currency, booking.currency, as_of=booking.date_from
                )
            except NoRateAvailable:
                logger.warning("data_migration.charge_item_fx_failed", reason="no_rate", **fx_ctx)
                raise
            # Quantise to the column's 2dp as well as the currency's minor
            # unit: a 3dp booking currency could otherwise pass the zero
            # guard here and still round to 0.00 (IntegrityError) at write.
            amount = quantise_money(original * rate.rate, booking.currency).quantize(
                Decimal("0.01")
            )
            if amount == 0:
                logger.warning("data_migration.charge_item_fx_rounded_to_zero", **fx_ctx)
                self._drop_stale(row)
                return None
            # Self-verifying provenance: record the applied rate so a later
            # backdated-rate correction (which reprices on re-run) is visible.
            provenance = (
                f"Imported from legacy: {quantise_money(original, row_currency)} "
                f"{row_currency.code} @ {rate.rate.normalize()} (as of {rate.as_of})."
            )

        notes_text = (row.get("Notes") or "").strip()
        # Label truncation must not lose customer-facing text.
        notes = notes_text if len(notes_text) > 200 else ""
        if provenance:
            notes = f"{notes}\n{provenance}" if notes else provenance
        return {
            "booking": booking,
            "label": notes_text[:200],
            "amount": amount,
            "currency": booking.currency,
            "notes": notes,
        }
