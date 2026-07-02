"""BookingChargeItemLoader (GAP-017).

Legacy `VillaBookingDetails` rows are staff-entered "Chargeable Extras" —
customer-facing manual money lines. The loader ports them as
`BookingChargeItem` rows pinned to the booking currency and suppresses the
`booking_total_changed` payment-schedule resync for the duration of the load:
imported bookings hold PENDING BALANCE payments (PaymentLoader defaults
unknown legacy statuses to PENDING) that the resync would otherwise rewrite.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from unittest import mock

import pytest

from data_migration.base import LoadReport
from data_migration.loaders.bookings import (
    BookingChargeItemLoader,
    BookingLoader,
    _suppress_schedule_resync,
)
from payments.enums import PaymentMethod, PaymentPurpose, PaymentStatus
from payments.models.payment import Payment
from pricing.models.currency import Currency, FxRate
from properties.models.property import Property
from reservations.models.booking import Booking
from reservations.models.charge_item import BookingChargeItem


@pytest.fixture
def booking(seeded: Property) -> Booking:
    """A legacy-imported booking (legacy_id="7", currency GBP) minted via the
    real loader — the state BookingChargeItemLoader finds at cutover."""
    BookingLoader()._process_row(
        {
            "Id": 7,
            "VillaId": 900,
            "Guest": 55,
            "FromDate": date(2026, 6, 10),
            "ToDate": date(2026, 6, 17),
            "RentalPrice": Decimal("1400.00"),
            "BalanceDue": datetime(2026, 5, 15, 0, 0),
            "CurrencyId": 2,
            "QuotationNo": 1805,
        },
        LoadReport(loader="booking"),
    )
    return Booking.objects.get(legacy_id="7")


def _row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "Id": 31,
        "BookingId": 7,
        "CurrencyId": 2,
        "Price": Decimal("150.00"),
        "Notes": "Chef service",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# transform
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_transform_maps_notes_price_and_pins_booking_currency(booking: Booking) -> None:
    kwargs = BookingChargeItemLoader().transform(_row())

    assert kwargs is not None
    assert kwargs["booking"] == booking
    assert kwargs["label"] == "Chef service"
    assert kwargs["amount"] == Decimal("150.00")
    assert kwargs["currency"] == booking.currency
    assert kwargs["notes"] == ""


@pytest.mark.django_db
def test_transform_preserves_negative_amounts(booking: Booking) -> None:
    """Signed lines: negative = credit (e.g. a negotiated discount)."""
    kwargs = BookingChargeItemLoader().transform(
        _row(Price=Decimal("-400.00"), Notes="Negotiated rate adjustment")
    )

    assert kwargs is not None
    assert kwargs["amount"] == Decimal("-400.00")


@pytest.mark.django_db
def test_transform_skips_unresolvable_and_zero_booking_ids(booking: Booking) -> None:
    assert BookingChargeItemLoader().transform(_row(BookingId=999)) is None
    # BookingId=0 occurs in real legacy data (no FK constraint on the table).
    assert BookingChargeItemLoader().transform(_row(BookingId=0)) is None


@pytest.mark.django_db
def test_transform_skips_zero_price_rows(booking: Booking) -> None:
    """amount=0 violates `bookingchargeitem_amount_nonzero`; skip, not error."""
    assert BookingChargeItemLoader().transform(_row(Price=Decimal("0.00"))) is None


@pytest.mark.django_db
def test_transform_errors_on_unparseable_price(booking: Booking) -> None:
    """A money line that can't be parsed must land in `report.errors`, not
    vanish into the skipped count like a legitimate zero."""
    with pytest.raises(ValueError, match="unparseable Price"):
        BookingChargeItemLoader().transform(_row(Price="not-money"))


@pytest.mark.django_db
def test_transform_treats_zero_currency_as_booking_currency(booking: Booking) -> None:
    """CurrencyId=0 means "no currency" in legacy (rows summed blind into the
    booking total), so it pins to the booking currency."""
    kwargs = BookingChargeItemLoader().transform(_row(CurrencyId=0))

    assert kwargs is not None
    assert kwargs["currency"] == booking.currency


@pytest.mark.django_db
def test_transform_errors_on_unresolvable_nonzero_currency(booking: Booking) -> None:
    """A non-zero CurrencyId that doesn't resolve could be a genuinely foreign
    currency — writing it verbatim is the exact money bug GAP-017 forbids."""
    with pytest.raises(ValueError, match="unresolvable CurrencyId"):
        BookingChargeItemLoader().transform(_row(CurrencyId=424242))


@pytest.mark.django_db
def test_transform_truncates_long_notes_into_label_keeping_full_text(
    booking: Booking,
) -> None:
    long_text = "x" * 250
    kwargs = BookingChargeItemLoader().transform(_row(Notes=long_text))

    assert kwargs is not None
    assert kwargs["label"] == "x" * 200
    assert kwargs["notes"] == long_text


@pytest.mark.django_db
def test_transform_ports_empty_notes_as_empty_label(booking: Booking) -> None:
    """Legacy showed the empty string to guests — port it, don't invent text."""
    kwargs = BookingChargeItemLoader().transform(_row(Notes=""))

    assert kwargs is not None
    assert kwargs["label"] == ""


# ---------------------------------------------------------------------------
# _process_row / idempotency
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_process_row_writes_charge_item_keyed_on_legacy_id(booking: Booking) -> None:
    report = LoadReport(loader="booking_charge_item")
    BookingChargeItemLoader()._process_row(_row(), report)

    item = BookingChargeItem.objects.get(legacy_id="31")
    assert item.booking == booking
    assert item.label == "Chef service"
    assert item.amount == Decimal("150.00")
    assert item.currency == booking.currency
    assert report.created == 1


@pytest.mark.django_db
def test_loader_is_idempotent(booking: Booking) -> None:
    report = LoadReport(loader="booking_charge_item")
    BookingChargeItemLoader()._process_row(_row(), report)
    BookingChargeItemLoader()._process_row(_row(Notes="Chef service (updated)"), report)

    assert BookingChargeItem.objects.filter(legacy_id="31").count() == 1
    assert BookingChargeItem.objects.get(legacy_id="31").label == "Chef service (updated)"
    assert (report.created, report.updated) == (1, 1)


# ---------------------------------------------------------------------------
# full-reload removal sweep
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_load_rows_removes_rows_hard_deleted_in_legacy(booking: Booking) -> None:
    """Legacy hard-deletes "Chargeable Extras" (the table has no DeletedAt) and
    this loader always reads the full table, so a row that vanished from legacy
    must vanish here too — or a deleted money line keeps inflating the total."""
    loader = BookingChargeItemLoader()
    loader._load_rows([_row(Id=31), _row(Id=32, Notes="Boat hire")], LoadReport(loader="x"))
    assert BookingChargeItem.objects.filter(legacy_id__isnull=False).count() == 2

    loader._load_rows([_row(Id=32, Notes="Boat hire")], LoadReport(loader="x"))

    assert not BookingChargeItem.objects.filter(legacy_id="31").exists()
    assert BookingChargeItem.objects.filter(legacy_id="32").exists()


@pytest.mark.django_db
def test_removal_sweep_spares_staff_created_rows(booking: Booking) -> None:
    """Only legacy-loaded rows (legacy_id set) mirror legacy deletions."""
    staff_row = BookingChargeItem.objects.create(
        booking=booking,
        label="Staff-added charge",
        amount=Decimal("25.00"),
        currency=booking.currency,
    )

    BookingChargeItemLoader()._load_rows([_row()], LoadReport(loader="x"))

    assert BookingChargeItem.objects.filter(pk=staff_row.pk).exists()


# ---------------------------------------------------------------------------
# schedule-resync suppression
# ---------------------------------------------------------------------------


def _pending_balance_payment(booking: Booking) -> Payment:
    """The shape PaymentLoader mints: unknown legacy status → PENDING BALANCE."""
    return Payment.objects.create(
        booking=booking,
        purpose=PaymentPurpose.BALANCE,
        status=PaymentStatus.PENDING,
        amount=Decimal("999.99"),
        currency=booking.currency,
        payment_method=PaymentMethod.CARD,
        legacy_id="d-1",
    )


@pytest.mark.django_db
def test_load_rows_does_not_resync_schedules(booking: Booking) -> None:
    """The GAP-017 invariant: loading historical charge lines must not resize
    live payment schedules (or security deposits)."""
    payment = _pending_balance_payment(booking)

    with (
        mock.patch(
            "payments.services.payment_scheduler.PaymentScheduler.resync_for_booking"
        ) as resync,
        mock.patch(
            "payments.services.security_deposit.SecurityDepositService.resize_for_booking"
        ) as resize,
    ):
        report = LoadReport(loader="booking_charge_item")
        BookingChargeItemLoader()._load_rows([_row()], report)

    assert report.created == 1
    resync.assert_not_called()
    resize.assert_not_called()
    payment.refresh_from_db()
    assert payment.amount == Decimal("999.99")


@pytest.mark.django_db
def test_resync_receiver_active_again_after_load(booking: Booking) -> None:
    BookingChargeItemLoader()._load_rows([_row()], LoadReport(loader="booking_charge_item"))

    with mock.patch(
        "payments.services.payment_scheduler.PaymentScheduler.resync_for_booking"
    ) as resync:
        BookingChargeItem.objects.create(
            booking=booking,
            label="Post-load staff charge",
            amount=Decimal("10.00"),
            currency=booking.currency,
        )

    resync.assert_called_once_with(booking)


@pytest.mark.django_db
def test_suppress_cm_reconnects_exactly_once_even_on_error(booking: Booking) -> None:
    with pytest.raises(RuntimeError, match="boom"):
        with _suppress_schedule_resync():
            raise RuntimeError("boom")
    # Repeated use must not stack duplicate receivers (same dispatch_uid).
    with _suppress_schedule_resync():
        pass

    with mock.patch(
        "payments.services.payment_scheduler.PaymentScheduler.resync_for_booking"
    ) as resync:
        BookingChargeItem.objects.create(
            booking=booking,
            label="After CM error",
            amount=Decimal("10.00"),
            currency=booking.currency,
        )

    resync.assert_called_once_with(booking)


@pytest.mark.django_db
def test_suppress_cm_is_reentrant_and_restores_prior_state(booking: Booking) -> None:
    """The inner CM of a nested pair must not end the outer suppression, and
    the CM must not force-connect a receiver that was already disconnected
    before entry (e.g. by a test or an ops shell)."""
    from reservations.signals import booking_total_changed

    with mock.patch(
        "payments.services.payment_scheduler.PaymentScheduler.resync_for_booking"
    ) as resync:
        with _suppress_schedule_resync():
            with _suppress_schedule_resync():
                pass
            # Still inside the outer window: the inner exit must not have
            # reconnected the receiver.
            BookingChargeItem.objects.create(
                booking=booking,
                label="Inside outer window",
                amount=Decimal("10.00"),
                currency=booking.currency,
            )
        resync.assert_not_called()

    # Prior-state restore: a deliberate pre-existing disconnect survives the CM.
    was_connected = booking_total_changed.disconnect(
        dispatch_uid="payments.resync_on_booking_total_changed"
    )
    assert was_connected
    try:
        with _suppress_schedule_resync():
            pass
        with mock.patch(
            "payments.services.payment_scheduler.PaymentScheduler.resync_for_booking"
        ) as resync:
            BookingChargeItem.objects.create(
                booking=booking,
                label="While deliberately disconnected",
                amount=Decimal("10.00"),
                currency=booking.currency,
            )
        resync.assert_not_called()
    finally:
        from payments.signals import _resync_schedule_on_booking_total_changed

        booking_total_changed.connect(
            _resync_schedule_on_booking_total_changed,
            dispatch_uid="payments.resync_on_booking_total_changed",
        )


# ---------------------------------------------------------------------------
# FX convert-or-flag (mismatched currencies)
# ---------------------------------------------------------------------------


@pytest.fixture
def usd(db: None) -> Currency:
    return Currency.objects.create(code="USD", name="US Dollar", symbol="$", legacy_id="3")


@pytest.mark.django_db
def test_mismatched_currency_converts_at_booking_date_from(booking: Booking, usd: Currency) -> None:
    """Convert via the most recent rate ≤ booking.date_from (pinned so
    re-runs are deterministic), quantised to the booking currency, with
    self-verifying rate provenance kept in notes."""
    FxRate.objects.create(base=usd, quote=booking.currency, rate="0.80", as_of=date(2026, 6, 1))
    # A later rate after date_from must NOT win — determinism on re-runs.
    FxRate.objects.create(base=usd, quote=booking.currency, rate="0.90", as_of=date(2026, 6, 15))

    kwargs = BookingChargeItemLoader().transform(_row(CurrencyId=3, Price=Decimal("100.00")))

    assert kwargs is not None
    assert kwargs["amount"] == Decimal("80.00")
    assert kwargs["currency"] == booking.currency
    assert kwargs["label"] == "Chef service"
    # Rate + as-of make the conversion auditable from the note alone (a
    # backdated-rate correction reprices on re-run and must be visible).
    assert "100.00 USD @ 0.8 (as of 2026-06-01)" in kwargs["notes"]


@pytest.mark.django_db
def test_conversion_provenance_appends_to_overflowed_notes(booking: Booking, usd: Currency) -> None:
    FxRate.objects.create(base=usd, quote=booking.currency, rate="0.80", as_of=date(2026, 6, 1))
    long_text = "x" * 250

    kwargs = BookingChargeItemLoader().transform(
        _row(CurrencyId=3, Price=Decimal("100.00"), Notes=long_text)
    )

    assert kwargs is not None
    assert kwargs["label"] == "x" * 200
    assert long_text in kwargs["notes"]
    assert "100.00 USD" in kwargs["notes"]


@pytest.mark.django_db
def test_no_rate_available_flags_row_for_manual_review(booking: Booking, usd: Currency) -> None:
    """The ticket's flag path: no FxRate → the row lands in report.errors
    (ops seeds a rate and re-runs; the load is idempotent) with a warning."""
    import structlog.testing

    report = LoadReport(loader="booking_charge_item")
    with structlog.testing.capture_logs() as logs:
        BookingChargeItemLoader()._process_row(_row(CurrencyId=3), report)

    assert not BookingChargeItem.objects.filter(legacy_id="31").exists()
    assert len(report.errors) == 1
    assert report.errors[0][0] == "31"
    assert "NoRateAvailable" in report.errors[0][1]
    assert any(
        log["event"] == "data_migration.charge_item_fx_failed" and log["reason"] == "no_rate"
        for log in logs
    )


@pytest.mark.django_db
def test_conversion_rounding_to_zero_skips_with_warning(booking: Booking, usd: Currency) -> None:
    """A converted amount that quantises to 0.00 would violate the amount!=0
    constraint — skip it with a warning rather than an opaque IntegrityError."""
    import structlog.testing

    FxRate.objects.create(base=usd, quote=booking.currency, rate="0.10", as_of=date(2026, 6, 1))

    report = LoadReport(loader="booking_charge_item")
    with structlog.testing.capture_logs() as logs:
        BookingChargeItemLoader()._process_row(_row(CurrencyId=3, Price=Decimal("0.01")), report)

    assert not BookingChargeItem.objects.filter(legacy_id="31").exists()
    assert report.skipped == 1
    assert report.errors == []
    assert any(log["event"] == "data_migration.charge_item_fx_rounded_to_zero" for log in logs)


@pytest.mark.django_db
def test_zero_outcomes_drop_a_previously_loaded_line(booking: Booking, usd: Currency) -> None:
    """A zero outcome (legacy Price zeroed, or a corrected rate now rounding
    to zero) must delete the stale line an earlier run wrote — the removal
    sweep can't (skipped rows stay in its `seen` set)."""
    report = LoadReport(loader="booking_charge_item")
    BookingChargeItemLoader()._process_row(_row(), report)
    assert BookingChargeItem.objects.filter(legacy_id="31").exists()

    # Legacy Price edited to zero between runs.
    BookingChargeItemLoader()._process_row(_row(Price=Decimal("0.00")), report)
    assert not BookingChargeItem.objects.filter(legacy_id="31").exists()

    # Re-load, then a corrected FxRate makes the conversion round to zero.
    BookingChargeItemLoader()._process_row(_row(), report)
    FxRate.objects.create(base=usd, quote=booking.currency, rate="0.10", as_of=date(2026, 6, 1))
    BookingChargeItemLoader()._process_row(_row(CurrencyId=3, Price=Decimal("0.01")), report)
    assert not BookingChargeItem.objects.filter(legacy_id="31").exists()


# ---------------------------------------------------------------------------
# --since
# ---------------------------------------------------------------------------


def test_since_is_ignored_with_a_warning() -> None:
    """VillaBookingDetails has no UpdatedAt and the removal sweep needs the
    full row set — `--since` must not narrow the query (RateBandLoader idiom)."""
    import structlog.testing

    loader = BookingChargeItemLoader(since="2026-01-01T00:00:00")
    with structlog.testing.capture_logs() as logs:
        assert loader._apply_since(loader.legacy_query) == loader.legacy_query

    assert any(log["event"] == "data_migration.charge_item_since_ignored" for log in logs)
