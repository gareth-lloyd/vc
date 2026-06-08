"""Integration tests for ICalIngestService — the per-villa feed poller.

Feeds are mocked with `respx` (httpx-native); each test drives the reconciler
through one or more `run()` calls and asserts the resulting OwnerBlock state,
awareness-feed rows, conflict signal, and availability surface.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

import httpx
import pytest
import respx
from django.utils import timezone

from integrations.enums import SyncProvider, SyncStatus
from integrations.models import SyncRecord
from properties.factories import PropertyCalendarFeedFactory
from reservations.enums import (
    BookingHoldReason,
    BookingStatus,
    OwnerBlockSource,
    OwnerBlockStatus,
    OwnerBlockUpdateKind,
    PaymentMethod,
)
from reservations.models import Booking, OwnerBlock, Quotation, QuotationLine
from reservations.services.availability import AvailabilityService
from reservations.services.holds import HoldService
from reservations.services.ical_ingest import ICalIngestService
from reservations.signals import ical_conflict_detected

if TYPE_CHECKING:
    from pricing.models import Currency
    from properties.models import Property, PropertyCalendarFeed
    from reservations.models import Guest, TermsVersion

pytestmark = pytest.mark.django_db


def _ics(*ranges: tuple[str, str], uid_prefix: str = "evt") -> str:
    """Build an all-day-event calendar from (dtstart, dtend) date strings."""
    events = []
    for i, (start, end) in enumerate(ranges):
        events.append(
            "BEGIN:VEVENT\r\n"
            f"UID:{uid_prefix}-{i}\r\n"
            "SUMMARY:Reserved\r\n"
            f"DTSTART;VALUE=DATE:{start}\r\n"
            f"DTEND;VALUE=DATE:{end}\r\n"
            "END:VEVENT\r\n"
        )
    body = "".join(events)
    return f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//t//EN\r\n{body}END:VCALENDAR\r\n"


def _feed(property_: Property, url: str, label: str = "Airbnb") -> PropertyCalendarFeed:
    return cast(
        "PropertyCalendarFeed",
        PropertyCalendarFeedFactory(property=property_, url=url, label=label),
    )


def _booking(
    *,
    property: Property,
    guest: Guest,
    currency: Currency,
    terms: TermsVersion,
    date_from: date,
    date_to: date,
) -> Booking:
    quotation = Quotation.objects.create(
        enquiry=guest.enquiries.create(),
        guest=guest,
        currency=currency,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    line = QuotationLine.objects.create(
        quotation=quotation,
        property=property,
        date_from=date_from,
        date_to=date_to,
        adults=2,
        total=Decimal("1400.00"),
    )
    return Booking.objects.create(
        quotation_line=line,
        guest=guest,
        property=property,
        date_from=date_from,
        date_to=date_to,
        adults=2,
        currency=currency,
        terms_version=terms,
        terms_accepted_at=timezone.now(),
        payment_method=PaymentMethod.CARD.value,
        status=BookingStatus.AWAITING_DEPOSIT.value,
    )


@respx.mock
def test_import_creates_owner_block(property_: Property) -> None:
    url = "https://example.test/a.ics"
    _feed(property_, url)
    respx.get(url).mock(return_value=httpx.Response(200, text=_ics(("20260701", "20260705"))))

    [result] = ICalIngestService.run()

    assert result.created == 1
    block = OwnerBlock.objects.get(property=property_, source=OwnerBlockSource.ICAL.value)
    assert block.status == OwnerBlockStatus.APPROVED.value
    assert block.created_by_id is None
    assert block.date_from == date(2026, 7, 1)
    assert block.date_to == date(2026, 7, 5)
    assert block.resulting_hold is not None
    assert block.resulting_hold.is_live() is True
    # awareness-feed parity with owner-created blocks
    update = block.updates.get()
    assert update.kind == OwnerBlockUpdateKind.CREATED.value
    assert update.actor_id is None


@respx.mock
def test_repoll_is_idempotent(property_: Property) -> None:
    url = "https://example.test/a.ics"
    _feed(property_, url)
    respx.get(url).mock(return_value=httpx.Response(200, text=_ics(("20260701", "20260705"))))

    ICalIngestService.run()
    ICalIngestService.run()

    assert (
        OwnerBlock.objects.filter(
            property=property_,
            source=OwnerBlockSource.ICAL.value,
            status=OwnerBlockStatus.APPROVED.value,
        ).count()
        == 1
    )


@respx.mock
def test_vanished_event_cancels_block(property_: Property) -> None:
    url = "https://example.test/a.ics"
    _feed(property_, url)
    route = respx.get(url)

    route.mock(return_value=httpx.Response(200, text=_ics(("20260701", "20260705"))))
    ICalIngestService.run()

    # Event removed from the feed → its block is cancelled and the hold released.
    route.mock(return_value=httpx.Response(200, text=_ics()))
    [result] = ICalIngestService.run()

    assert result.cancelled == 1
    block = OwnerBlock.objects.get(property=property_, source=OwnerBlockSource.ICAL.value)
    assert block.status == OwnerBlockStatus.CANCELLED.value
    assert block.resulting_hold is not None
    assert block.resulting_hold.is_live() is False
    kinds = list(block.updates.order_by("created_at").values_list("kind", flat=True))
    assert kinds == [OwnerBlockUpdateKind.CREATED.value, OwnerBlockUpdateKind.CANCELLED.value]


@respx.mock
def test_cross_feed_overlap_coalesces_into_one_block(property_: Property) -> None:
    url_a = "https://example.test/a.ics"
    url_b = "https://example.test/b.ics"
    _feed(property_, url_a, label="Airbnb")
    _feed(property_, url_b, label="Vrbo")
    # Same booking reported by both feeds, plus an adjacent night on one of them.
    respx.get(url_a).mock(return_value=httpx.Response(200, text=_ics(("20260701", "20260705"))))
    respx.get(url_b).mock(return_value=httpx.Response(200, text=_ics(("20260704", "20260708"))))

    [result] = ICalIngestService.run()

    assert result.created == 1
    block = OwnerBlock.objects.get(property=property_, source=OwnerBlockSource.ICAL.value)
    assert block.date_from == date(2026, 7, 1)
    assert block.date_to == date(2026, 7, 8)


@respx.mock
def test_booking_conflict_skips_write_and_fires_signal(
    property_: Property, guest: Guest, gbp: Currency, terms: TermsVersion
) -> None:
    url = "https://example.test/a.ics"
    _feed(property_, url)
    _booking(
        property=property_,
        guest=guest,
        currency=gbp,
        terms=terms,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 5),
    )
    respx.get(url).mock(return_value=httpx.Response(200, text=_ics(("20260702", "20260706"))))

    received: list[dict[str, Any]] = []

    def _receiver(sender: object, **kwargs: Any) -> None:
        received.append(kwargs)

    ical_conflict_detected.connect(_receiver, dispatch_uid="test.ical.conflict")
    try:
        [result] = ICalIngestService.run()
    finally:
        ical_conflict_detected.disconnect(dispatch_uid="test.ical.conflict")

    assert result.conflicts == 1
    assert result.created == 0
    # No owner block was written over the live booking.
    assert not OwnerBlock.objects.filter(
        property=property_, source=OwnerBlockSource.ICAL.value
    ).exists()
    assert len(received) == 1
    assert received[0]["property"].pk == property_.pk
    assert received[0]["booking"] is not None


@respx.mock
def test_feed_error_skips_property_without_cancelling(property_: Property) -> None:
    url = "https://example.test/a.ics"
    _feed(property_, url)
    route = respx.get(url)

    route.mock(return_value=httpx.Response(200, text=_ics(("20260701", "20260705"))))
    ICalIngestService.run()

    # Feed now 500s — the property is skipped, existing block must NOT be cancelled.
    route.mock(return_value=httpx.Response(500))
    [result] = ICalIngestService.run()

    assert result.skipped is True
    assert result.cancelled == 0
    block = OwnerBlock.objects.get(property=property_, source=OwnerBlockSource.ICAL.value)
    assert block.status == OwnerBlockStatus.APPROVED.value


@respx.mock
def test_partial_feed_failure_skips_reconcile(property_: Property) -> None:
    url_a = "https://example.test/a.ics"
    url_b = "https://example.test/b.ics"
    feed_a = _feed(property_, url_a, label="Airbnb")
    _feed(property_, url_b, label="Vrbo")

    respx.get(url_a).mock(return_value=httpx.Response(200, text=_ics(("20260701", "20260705"))))
    respx.get(url_b).mock(return_value=httpx.Response(503))

    [result] = ICalIngestService.run()

    assert result.skipped is True
    assert result.created == 0
    assert not OwnerBlock.objects.filter(
        property=property_, source=OwnerBlockSource.ICAL.value
    ).exists()
    # The healthy feed still records its poll state + SyncRecord.
    feed_a.refresh_from_db()
    assert feed_a.last_status == "ok"


@respx.mock
def test_empty_feed_creates_nothing(property_: Property) -> None:
    url = "https://example.test/a.ics"
    feed = _feed(property_, url)
    respx.get(url).mock(return_value=httpx.Response(200, text=_ics()))

    [result] = ICalIngestService.run()

    assert result.created == 0
    assert result.skipped is False
    feed.refresh_from_db()
    assert feed.last_status == "ok"
    record = SyncRecord.objects.get(provider=SyncProvider.ICAL.value, object_id=feed.pk)
    assert record.status == SyncStatus.IN_SYNC.value


@respx.mock
def test_range_edit_updates_block_without_gap(property_: Property) -> None:
    """Extending an imported range re-keys it: the old block is cancelled first so
    the new range places cleanly (no HoldUnavailable, no availability gap)."""
    url = "https://example.test/a.ics"
    _feed(property_, url)
    route = respx.get(url)

    route.mock(return_value=httpx.Response(200, text=_ics(("20260701", "20260705"))))
    ICalIngestService.run()

    # Extend the booking by a night → a different idempotency key.
    route.mock(return_value=httpx.Response(200, text=_ics(("20260701", "20260706"))))
    [result] = ICalIngestService.run()

    assert result.created == 1
    assert result.cancelled == 1
    assert result.skipped_holds == 0
    approved = OwnerBlock.objects.filter(
        property=property_,
        source=OwnerBlockSource.ICAL.value,
        status=OwnerBlockStatus.APPROVED.value,
    )
    assert approved.count() == 1
    assert approved.get().date_to == date(2026, 7, 6)
    # The extra night is blocked — no gap opened during the swap.
    calendar = AvailabilityService.calendar(property_, date(2026, 7, 1), date(2026, 7, 7))
    assert calendar[date(2026, 7, 5)].available is False


@respx.mock
def test_quotation_hold_clash_fires_conflict(
    property_: Property, guest: Guest, gbp: Currency, terms: TermsVersion
) -> None:
    """An imported range overlapping an open-quotation hold is a real double-sell
    risk — VC is quoting dates booked elsewhere — so it escalates like a booking."""
    url = "https://example.test/a.ics"
    _feed(property_, url)
    quotation = Quotation.objects.create(
        enquiry=guest.enquiries.create(),
        guest=guest,
        currency=gbp,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    HoldService.place(
        property=property_,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 5),
        reason=BookingHoldReason.QUOTATION_OPEN.value,
        quotation=quotation,
        expires_at=timezone.now() + timedelta(days=2),
    )
    respx.get(url).mock(return_value=httpx.Response(200, text=_ics(("20260702", "20260706"))))

    received: list[dict[str, Any]] = []

    def _receiver(sender: object, **kwargs: Any) -> None:
        received.append(kwargs)

    ical_conflict_detected.connect(_receiver, dispatch_uid="test.ical.quotation_clash")
    try:
        [result] = ICalIngestService.run()
    finally:
        ical_conflict_detected.disconnect(dispatch_uid="test.ical.quotation_clash")

    assert result.conflicts == 1
    assert result.created == 0
    assert result.skipped_holds == 0
    assert not OwnerBlock.objects.filter(
        property=property_, source=OwnerBlockSource.ICAL.value
    ).exists()
    assert len(received) == 1
    assert received[0]["conflict_kind"] == "quotation"
    assert received[0]["booking"] is None


@respx.mock
def test_benign_hold_overlap_is_skipped_silently(property_: Property) -> None:
    """A manual owner-side hold the operator owns is not escalated — just skipped."""
    url = "https://example.test/a.ics"
    _feed(property_, url)
    HoldService.place(
        property=property_,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 5),
        never_expires=True,
        reason=BookingHoldReason.MANUAL.value,
    )
    respx.get(url).mock(return_value=httpx.Response(200, text=_ics(("20260702", "20260706"))))

    received: list[dict[str, Any]] = []

    def _receiver(sender: object, **kwargs: Any) -> None:
        received.append(kwargs)

    ical_conflict_detected.connect(_receiver, dispatch_uid="test.ical.benign_hold")
    try:
        [result] = ICalIngestService.run()
    finally:
        ical_conflict_detected.disconnect(dispatch_uid="test.ical.benign_hold")

    assert result.conflicts == 0
    assert result.skipped_holds == 1
    assert result.created == 0
    assert len(received) == 0


@respx.mock
def test_malformed_feed_recorded_as_error_without_crashing(property_: Property) -> None:
    """A non-calendar payload is a parse (ValueError) failure: recorded on the feed,
    the property skipped, the run continues — it never crashes the batch."""
    url = "https://example.test/a.ics"
    feed = _feed(property_, url)
    respx.get(url).mock(return_value=httpx.Response(200, text="this is not a calendar"))

    [result] = ICalIngestService.run()

    assert result.skipped is True
    feed.refresh_from_db()
    assert feed.last_status == "error"


@respx.mock
def test_availability_surfaces_imported_block(property_: Property) -> None:
    url = "https://example.test/a.ics"
    _feed(property_, url)
    respx.get(url).mock(return_value=httpx.Response(200, text=_ics(("20260701", "20260705"))))

    ICalIngestService.run()

    calendar = AvailabilityService.calendar(property_, date(2026, 7, 1), date(2026, 7, 6))
    # Half-open [01, 05) → nights 1..4 are blocked, 5 is free again.
    assert calendar[date(2026, 7, 1)].available is False
    assert calendar[date(2026, 7, 1)].reason == "owner_block"
    assert calendar[date(2026, 7, 4)].available is False
    assert calendar[date(2026, 7, 5)].available is True
