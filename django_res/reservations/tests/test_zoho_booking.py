"""Tests for the Booking → Zoho Flow push (GAP-082 Unit 6).

Booking registers with `auto_push=True` and NO ignore set: every transition
ends in `Booking._transition`'s `.save(update_fields=[...])` — all meaningful,
low-frequency. Registered by `reservations.apps.ready()` — never unregistered
in tests (xdist worker leak); behaviour toggled via
`override_settings(ZOHO_FLOW_WEBHOOKS=…)`.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast
from unittest import mock

import pytest
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.test import override_settings
from django.utils import timezone

from accounts.factories import PersonFactory
from core.tests import assert_max_queries
from integrations import tasks
from integrations.enums import SyncProvider, SyncStatus
from integrations.models import SyncRecord
from integrations.services.zoho_flow import enqueue_zoho_push, get_zoho_spec
from reservations.enums import BookingGuestRole, BookingStatus
from reservations.models import Booking, BookingGuest, Enquiry, Quotation, QuotationLine
from reservations.services.bookings import BookingService
from reservations.services.zoho_payload import (
    build_booking_payload,
    build_quotation_payload,
)

if TYPE_CHECKING:
    from accounts.models import Person
    from pricing.models import Currency, RateBand
    from properties.models import Property
    from reservations.models import TermsVersion

BOOKING_URL = "https://flow.zoho.example/booking"
WEBHOOKS = {"contact": "", "villa": "", "enquiry": "", "quote": "", "booking": BOOKING_URL}

pytestmark = pytest.mark.django_db


@pytest.fixture
def delay_mock(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    m = mock.Mock()
    monkeypatch.setattr(tasks.push_sync_record, "delay", m)
    return m


@pytest.fixture
def booking(quotation_line: QuotationLine, terms: TermsVersion) -> Booking:
    # Built without a webhook URL (test settings pin all kinds to "") so no
    # SyncRecord exists yet; enqueue tests opt in via override_settings.
    return BookingService.create_from_quotation_line(quotation_line, terms)


def _booking_ct() -> ContentType:
    return ContentType.objects.get_for_model(Booking)


def _record_for(booking: Booking) -> SyncRecord:
    return SyncRecord.objects.get(
        content_type=_booking_ct(),
        object_id=booking.pk,
        provider=SyncProvider.ZOHO_CRM.value,
    )


def _mark_in_sync(record: SyncRecord) -> None:
    record.status = SyncStatus.IN_SYNC.value
    record.save(update_fields=["status", "updated_at"])


# --- registration ---------------------------------------------------------


def test_booking_is_registered_with_auto_push_on() -> None:
    spec = get_zoho_spec(Booking)
    assert spec is not None
    assert spec.kind == "booking"
    assert spec.auto_push is True
    assert spec.ignore_update_fields == frozenset()
    assert spec.build_payload is build_booking_payload


# --- payload --------------------------------------------------------------


def test_payload_core_fields(booking: Booking, property_: Property) -> None:
    payload = build_booking_payload(booking)

    assert payload["RES_ID"] == booking.pk
    assert payload["id"] == booking.pk
    assert payload["reference"] == booking.reference
    assert payload["legacy_id"] is None
    assert payload["status"] == BookingStatus.AWAITING_DEPOSIT.value
    assert payload["property"]["RES_ID"] == property_.pk
    assert payload["property"]["region"]["country"]["iso2"] == "GB"
    assert payload["date_from"] == "2026-06-10"
    assert payload["date_to"] == "2026-06-17"
    assert payload["nights"] == 7
    assert payload["adults"] == 2
    assert payload["children"] == 0
    assert payload["currency"] == "GBP"
    assert payload["site_source"] == booking.site_source
    assert payload["payment_method"] == booking.payment_method
    assert payload["terms_version"] == {
        "RES_ID": booking.terms_version_id,
        "id": booking.terms_version_id,
        "version": booking.terms_version.version,
    }
    assert payload["terms_accepted_at"] == booking.terms_accepted_at.isoformat()
    assert payload["assigned_to"] is None
    assert payload["cancel_reason"] == ""
    assert payload["cancelled_at"] is None
    assert payload["is_archived"] is False
    assert payload["archived_at"] is None
    assert payload["created_at"] == booking.created_at.isoformat()
    assert payload["updated_at"] == booking.updated_at.isoformat()


def test_payload_person_and_agent_summaries(booking: Booking, customer: Person) -> None:
    agent = cast("Person", PersonFactory(first_name="Alan", last_name="Turing"))
    booking.agent = agent
    booking.save()

    payload = build_booking_payload(booking)

    assert payload["person"]["RES_ID"] == customer.pk
    assert payload["person"]["full_name"] == "Ada Lovelace"
    assert payload["person"]["primary_email"] == "ada@example.com"
    assert payload["agent"]["RES_ID"] == agent.pk
    assert payload["agent"]["full_name"] == "Alan Turing"


def test_payload_quote_and_enquiry_links(booking: Booking) -> None:
    quotation = booking.quotation_line.quotation
    enquiry = quotation.enquiry

    payload = build_booking_payload(booking)

    assert payload["quote"] == {
        "RES_ID": quotation.pk,
        "id": quotation.pk,
        "reference": quotation.reference,
        "number": quotation.number,
        "legacy_id": None,
        "is_synthetic": False,
    }
    assert payload["enquiry"] == {
        "RES_ID": enquiry.pk,
        "id": enquiry.pk,
        "reference": enquiry.reference,
    }


def test_payload_line_matches_quotation_payload_line(booking: Booking) -> None:
    """Shape parity is the contract: the booking's `line` must be EXACTLY what
    the quote push emits for the same QuotationLine, so Flow-side mappings can
    share one line schema."""
    quote_payload = build_quotation_payload(booking.quotation_line.quotation)

    payload = build_booking_payload(booking)

    assert payload["line"] == quote_payload["lines"][0]
    assert payload["line"]["RES_ID"] == booking.quotation_line_id


def test_payload_flags_synthetic_legacy_quote(booking: Booking) -> None:
    """Booking-synthesised quotations (legacy_id `booking-*`) never push as
    the quote kind, so the flag prevents dangling Flow joins."""
    quotation = booking.quotation_line.quotation
    quotation.legacy_id = "booking-123"
    quotation.save(update_fields=["legacy_id", "updated_at"])

    payload = build_booking_payload(booking)

    assert payload["quote"]["is_synthetic"] is True


def test_payload_booking_date_is_created_at(booking: Booking) -> None:
    """`booking_date` (the historic-import filter) is created_at — the loader
    back-stamps created_at from legacy CreatedAt (Unit 8) so it's faithful."""
    payload = build_booking_payload(booking)

    assert payload["booking_date"] == booking.created_at.isoformat()
    assert payload["booking_date"] == payload["created_at"]


def test_payload_financials_is_explicit_null(booking: Booking) -> None:
    """Key presence pins the contract position for Flow pre-wiring; null can't
    read as "zero money". Content lands after the next Limitless call."""
    payload = build_booking_payload(booking)

    assert "financials" in payload
    assert payload["financials"] is None


def test_payload_anonymized_person_fails_closed(booking: Booking) -> None:
    booking.person.anonymize()
    booking.refresh_from_db()

    payload = build_booking_payload(booking)

    assert payload["person"] is None
    assert "[REDACTED]" not in json.dumps(payload)


def test_payload_json_round_trips(booking: Booking) -> None:
    payload = build_booking_payload(booking)
    assert json.loads(json.dumps(payload)) == payload


def test_payload_query_count_pinned(booking: Booking) -> None:
    """One SELECT via the select_related chain + 4 prefetch buckets
    (person/agent emails+phones) — dropping a leg regresses to lazy walks."""
    booking.agent = cast("Person", PersonFactory())
    booking.save()

    with assert_max_queries(5):
        build_booking_payload(booking)


# --- enqueue wiring -------------------------------------------------------


@pytest.mark.usefixtures("run_on_commit_immediately")
def test_create_from_quotation_line_single_dispatch(
    quotation_line: QuotationLine,
    terms: TermsVersion,
    delay_mock: mock.Mock,
) -> None:
    """Create + LEAD BookingGuest + transition all enqueue inside one
    transaction — PENDING dedupe must collapse them to a single dispatch."""
    with override_settings(ZOHO_FLOW_WEBHOOKS=WEBHOOKS):
        booking = BookingService.create_from_quotation_line(quotation_line, terms)

    record = _record_for(booking)
    assert record.status == SyncStatus.PENDING
    assert SyncRecord.objects.filter(content_type=_booking_ct()).count() == 1
    assert delay_mock.call_count == 1


def test_dispatch_defers_until_commit_so_draft_is_never_delivered(
    quotation_line: QuotationLine,
    terms: TermsVersion,
    delay_mock: mock.Mock,
    django_capture_on_commit_callbacks: Any,
) -> None:
    """The payload is built at delivery time from the live row, and dispatch
    rides `transaction.on_commit` — by the time the task can run, the creation
    transaction (create + transition) has committed and status is past DRAFT.
    (Deliberately NOT `run_on_commit_immediately`: that fixture would run the
    dispatch mid-transaction while status is still DRAFT and invert the test.)
    """
    with override_settings(ZOHO_FLOW_WEBHOOKS=WEBHOOKS):
        with django_capture_on_commit_callbacks() as callbacks:
            booking = BookingService.create_from_quotation_line(quotation_line, terms)
            assert delay_mock.call_count == 0  # nothing dispatched mid-transaction

        for callback in callbacks:
            callback()

    assert delay_mock.call_count == 1
    booking.refresh_from_db()
    assert booking.status == BookingStatus.AWAITING_DEPOSIT.value


@pytest.mark.usefixtures("run_on_commit_immediately")
def test_record_deposit_bumps(booking: Booking, delay_mock: mock.Mock) -> None:
    with override_settings(ZOHO_FLOW_WEBHOOKS=WEBHOOKS):
        enqueue_zoho_push(booking)
        record = _record_for(booking)
        _mark_in_sync(record)

        booking.record_deposit()

    record.refresh_from_db()
    assert record.status == SyncStatus.PENDING


@pytest.mark.usefixtures("run_on_commit_immediately")
def test_modify_dates_bumps(
    booking: Booking,
    rate_rule: RateBand,
    delay_mock: mock.Mock,
) -> None:
    with override_settings(ZOHO_FLOW_WEBHOOKS=WEBHOOKS):
        enqueue_zoho_push(booking)
        record = _record_for(booking)
        _mark_in_sync(record)

        booking.modify_dates(date(2026, 7, 1), date(2026, 7, 8))

    record.refresh_from_db()
    assert record.status == SyncStatus.PENDING


@pytest.mark.usefixtures("run_on_commit_immediately")
def test_unset_url_is_full_noop(
    quotation_line: QuotationLine,
    terms: TermsVersion,
    delay_mock: mock.Mock,
) -> None:
    booking = BookingService.create_from_quotation_line(quotation_line, terms)
    booking.record_deposit()

    assert SyncRecord.objects.count() == 0
    delay_mock.assert_not_called()


@pytest.mark.usefixtures("run_on_commit_immediately")
def test_person_merge_re_enqueues_repointed_bookings(
    booking: Booking,
    terms: TermsVersion,
    gbp: Currency,
    property_: Property,
    delay_mock: mock.Mock,
) -> None:
    """`Person.merge` repoints booking FKs (person AND agent) via `.update()`
    — no post_save — so the person_merged receiver must re-enqueue every
    repointed booking now belonging to the survivor."""
    survivor = cast("Person", PersonFactory())
    absorbed = cast("Person", PersonFactory())
    # Absorbed as customer: a second booking whose person FK is the absorbed
    # person (Booking.person comes from Quotation.person at creation).
    quotation = Quotation.objects.create(
        enquiry=Enquiry.objects.create(person=absorbed),
        person=absorbed,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    line = QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        currency=gbp,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 8),
        adults=2,
        total=Decimal("1400.00"),
    )
    as_customer = BookingService.create_from_quotation_line(line, terms)
    # Absorbed as agent: the fixture booking, agent leg only.
    booking.agent = absorbed
    booking.save(update_fields=["agent", "updated_at"])

    with override_settings(ZOHO_FLOW_WEBHOOKS=WEBHOOKS):
        absorbed.merge(survivor)

    assert _record_for(as_customer).status == SyncStatus.PENDING
    assert _record_for(booking).status == SyncStatus.PENDING
    as_customer.refresh_from_db()
    booking.refresh_from_db()
    assert as_customer.person_id == survivor.pk
    assert booking.agent_id == survivor.pk


@pytest.mark.usefixtures("run_on_commit_immediately")
def test_non_lead_guest_save_does_not_enqueue(booking: Booking, delay_mock: mock.Mock) -> None:
    """Only the LEAD sync rewrites the payload's `person` — CO_TRAVELLER /
    other guest churn must not push (the receiver's role guard)."""
    with override_settings(ZOHO_FLOW_WEBHOOKS=WEBHOOKS):
        BookingGuest.objects.create(
            booking=booking,
            person=cast("Person", PersonFactory()),
            role=BookingGuestRole.CO_TRAVELLER.value,
        )

    assert not SyncRecord.objects.filter(content_type=_booking_ct()).exists()
    delay_mock.assert_not_called()


@pytest.mark.usefixtures("run_on_commit_immediately")
def test_lead_guest_swap_bumps(booking: Booking, delay_mock: mock.Mock) -> None:
    """The LEAD sync writes `Booking.person` via queryset `.update()` — no
    Booking post_save — yet the swap changes the payload's `person`; the
    BookingGuest receiver must bump the booking itself."""
    new_lead = cast("Person", PersonFactory(first_name="Grace", last_name="Hopper"))
    with override_settings(ZOHO_FLOW_WEBHOOKS=WEBHOOKS):
        enqueue_zoho_push(booking)
        record = _record_for(booking)
        _mark_in_sync(record)

        with transaction.atomic():
            lead = booking.booking_guests.get(role=BookingGuestRole.LEAD.value)
            lead.role = BookingGuestRole.CO_TRAVELLER.value
            lead.save()
            BookingGuest.objects.create(
                booking=booking,
                person=new_lead,
                role=BookingGuestRole.LEAD.value,
            )

    record.refresh_from_db()
    assert record.status == SyncStatus.PENDING
    booking.refresh_from_db()
    assert booking.person_id == new_lead.pk
