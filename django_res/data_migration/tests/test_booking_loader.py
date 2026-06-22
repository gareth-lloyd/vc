"""BookingLoader reference parity (GAP-006).

A legacy booking carries its `QuotationNo` forward as `VC{QuotationNo}` (same
digits as the originating `QVC{QuotationNo}` quotation). The synthesised
quotation must NOT claim that number — the real QuotationLoader owns it — so it
stays NULL with a per-booking sentinel reference. A booking with no QuotationNo
falls to a non-numeric `VC-TMP-…` sentinel, never a bare `VC{int}`.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from data_migration.base import LoadReport
from data_migration.loaders.bookings import BookingLoader
from data_migration.loaders.reservations import ClientLoader
from pricing.models.currency import Currency
from properties.models.property import Property
from reservations.models.booking import Booking


@pytest.fixture
def seeded(db: None) -> Property:
    from properties.models import Country, PropertyCategory, PropertyGroup, Region

    country, _ = Country.objects.get_or_create(
        iso2="GB", defaults={"name": "United Kingdom", "iso3": "GBR"}
    )
    region = Region.objects.create(country=country, name="South West", slug="south-west")
    category = PropertyCategory.objects.create(name="Villa", slug="villa")
    group = PropertyGroup.objects.create(name="Test group")
    prop = Property.objects.create(
        name="Test Villa",
        display_name="Test Villa",
        slug="test-villa",
        category=category,
        group=group,
        region=region,
        legacy_id="900",
    )
    # GAP-045 D5-3: the booking's customer is a `client-55` Person, written by
    # ClientLoader from a legacy VillaClientDetails row (Id=55) — the loader now
    # resolves it via `person_for_client`, no Guest in the graph.
    ClientLoader()._process_row(
        {
            "Id": 55,
            "FirstName": "Ada",
            "LastName": "Lovelace",
            "Email": "ada@example.com",
            "MobileNo": "",
        },
        LoadReport(loader="client"),
    )
    Currency.objects.create(code="GBP", name="Pound sterling", symbol="£", legacy_id="2")
    return prop


def _row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "Id": 7,
        "VillaId": 900,
        "Guest": 55,
        "FromDate": date(2026, 6, 10),
        "ToDate": date(2026, 6, 17),
        "RentalPrice": Decimal("1400.00"),
        # Legacy `VillaBooking.BalanceDue` is a DATETIME (the date the balance
        # falls due), not money — see ResSystem VillaBooking.cs.
        "BalanceDue": datetime(2026, 5, 15, 0, 0),
        "CurrencyId": 2,
        "QuotationNo": 1805,
    }
    base.update(overrides)
    return base


@pytest.mark.django_db
def test_booking_carries_quotationno_forward(seeded: Property) -> None:
    report = LoadReport(loader="booking")
    BookingLoader()._process_row(_row(), report)

    booking = Booking.objects.get(legacy_id="7")
    assert booking.reference == "VC1805"
    # Synthesised quotation must not claim the legacy number (the real
    # QuotationLoader owns `1805` on its own `QVC1805` row).
    assert booking.quotation_line.quotation.number is None


@pytest.mark.django_db
def test_booking_without_quotationno_uses_interim_sentinel(seeded: Property) -> None:
    report = LoadReport(loader="booking")
    BookingLoader()._process_row(_row(QuotationNo=None), report)

    booking = Booking.objects.get(legacy_id="7")
    assert booking.reference.startswith("VC-TMP")


@pytest.mark.django_db
def test_booking_money_fields_map_gross_and_due_date(seeded: Property) -> None:
    """`balance_due` is the rebuild's denormalised gross total (RentalPrice).

    Legacy `BalanceDue` is a datetime — the date the balance falls due — and
    maps to `balance_due_at`. The old guard (`isinstance(..., Decimal)`) could
    never pass, so every migrated booking landed with balance_due=0 and the
    staff UI rendered "Total 0.00 / Paid in full" for the whole legacy book.
    """
    report = LoadReport(loader="booking")
    BookingLoader()._process_row(_row(), report)

    booking = Booking.objects.get(legacy_id="7")
    assert booking.rental_price == Decimal("1400.00")
    assert booking.balance_due == Decimal("1400.00")
    assert booking.balance_due_at == date(2026, 5, 15)


@pytest.mark.django_db
def test_booking_balance_due_at_absent_when_legacy_date_missing(seeded: Property) -> None:
    report = LoadReport(loader="booking")
    BookingLoader()._process_row(_row(BalanceDue=None), report)

    booking = Booking.objects.get(legacy_id="7")
    assert booking.balance_due == Decimal("1400.00")
    assert booking.balance_due_at is None


@pytest.mark.django_db
def test_booking_loader_is_idempotent(seeded: Property) -> None:
    report = LoadReport(loader="booking")
    BookingLoader()._process_row(_row(), report)
    BookingLoader()._process_row(_row(), report)

    assert Booking.objects.filter(legacy_id="7").count() == 1
    assert Booking.objects.get(legacy_id="7").reference == "VC1805"


@pytest.mark.django_db
def test_booking_loader_writes_person_not_guest(seeded: Property) -> None:
    """GAP-045 D5-3: the loader resolves the customer via `person_for_client`
    (the `client-{id}` Person) and populates `person` (the authoritative customer
    FK), leaving the legacy `guest` leg NULL on the synthesised Quotation, the
    Booking, and its LEAD BookingGuest."""
    from data_migration.loaders._util import person_for_client
    from reservations.enums import BookingGuestRole
    from reservations.models.booking_guest import BookingGuest
    from reservations.models.quotation import Quotation

    BookingLoader()._process_row(_row(), LoadReport(loader="booking"))

    person = person_for_client(55)

    booking = Booking.objects.get(legacy_id="7")
    assert booking.person_id == person.pk

    quotation = Quotation.objects.get(legacy_id="booking-7")
    assert quotation.person_id == person.pk

    lead = BookingGuest.objects.get(booking=booking, role=BookingGuestRole.LEAD.value)
    assert lead.person_id == person.pk


@pytest.mark.django_db
def test_two_bookings_sharing_quotationno_are_preserved_with_suffix(seeded: Property) -> None:
    """A second legacy booking reusing a QuotationNo must be preserved with a
    uniquified `VC{n}-…` reference, not crash the import (the old behaviour
    raised IntegrityError on the unique `reference`)."""
    report = LoadReport(loader="booking")
    BookingLoader()._process_row(_row(Id=7, QuotationNo=1805), report)
    BookingLoader()._process_row(_row(Id=8, QuotationNo=1805), report)

    first = Booking.objects.get(legacy_id="7")
    second = Booking.objects.get(legacy_id="8")
    assert first.reference == "VC1805"
    assert second.reference.startswith("VC1805-")
    assert first.reference != second.reference

    # Re-running the loader leaves the suffixed reference untouched (idempotent).
    suffixed = second.reference
    BookingLoader()._process_row(_row(Id=8, QuotationNo=1805), report)
    second.refresh_from_db()
    assert second.reference == suffixed
