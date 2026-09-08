"""Tests for the Booking → Zoho Flow push (GAP-082 Unit 6).

Booking registers with `auto_push=True` and NO ignore set: every transition
ends in `Booking._transition`'s `.save(update_fields=[...])` — all meaningful,
low-frequency. Registered by `reservations.apps.ready()` — never unregistered
in tests (xdist worker leak); behaviour toggled via
`override_settings(ZOHO_FLOW_WEBHOOKS=…)`.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
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
    _iso,
    build_booking_payload,
    build_quotation_payload,
)

if TYPE_CHECKING:
    from accounts.models import Person
    from payments.models import Payment
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


# --- financials (GAP-085) -------------------------------------------------
#
# Contract from the 2026-07-29 Limitless call: res sends EVERY figure
# explicitly (Zoho formula fields can't reproduce non-proportional
# commission — GAP-076 pass-through extras + GAP-077 residual-on-BALANCE).
# Source of truth = owner_money_for_booking / payment_component_splits, the
# same authority the FinanceTab reads, so res-UI and Zoho can never disagree.

FINANCIALS_KEYS = frozenset(
    {
        "total_gross",
        "total_net",
        "gross_deposit",
        "net_deposit",
        "deposit_commission",
        "gross_balance",
        "net_balance",
        "balance_commission",
        # GAP-099: per-component payment state (raw PaymentStatus + ISO due_at).
        "deposit_status",
        "deposit_due_at",
        "balance_status",
        "balance_due_at",
    }
)

# GAP-079 worked example: GROSS 13%-VAT / 20%-commission villa, 10,000 split
# 30/70 — divides exactly, so figures are verifiable by hand.
FINANCIALS_SNAPSHOT = {
    "total": "10000.00",
    "commission": "1740.00",
    "tax": "1300.00",
    "net_to_owner": "6960.00",
    "price_basis": "gross",
}


def _set_snapshot(booking: Booking, snapshot: dict[str, Any]) -> None:
    booking.pricing_snapshot = snapshot
    booking.save(update_fields=["pricing_snapshot", "updated_at"])


def _payment(
    booking: Booking,
    *,
    purpose: str,
    amount: str,
    status: str = "pending",
    due_at: datetime | None = None,
) -> Payment:
    # Test scaffolding may import `payments` (layers contract ignores tests).
    from payments.models import Payment

    return Payment.objects.create(
        booking=booking,
        purpose=purpose,
        status=status,
        amount=Decimal(amount),
        currency=booking.currency,
        due_at=due_at,
    )


def _charge(
    booking: Booking,
    *,
    label: str,
    amount: str,
    commissionable: bool,
    category: str = "other",
) -> None:
    from reservations.models import BookingChargeItem

    BookingChargeItem.objects.create(
        booking=booking,
        label=label,
        amount=Decimal(amount),
        currency=booking.currency,
        commissionable=commissionable,
        category=category,
    )


def _funded_booking(
    booking: Booking,
    *,
    noncomm_charge: str | None = None,
    snapshot: dict[str, Any] | None = None,
) -> Booking:
    _set_snapshot(booking, snapshot if snapshot is not None else FINANCIALS_SNAPSHOT)
    if noncomm_charge is not None:
        # ⚠️ Charge items BEFORE Payment rows: the charge write fires
        # booking_total_changed → PaymentScheduler.resync_for_booking, which
        # rewrites PENDING rows (a no-op only on an empty schedule).
        _charge(booking, label="Chef pass-through", amount=noncomm_charge, commissionable=False)
    _payment(booking, purpose="deposit", amount="3000.00")
    _payment(booking, purpose="balance", amount="7000.00")
    return booking


def test_payload_financials_full_figures(booking: Booking) -> None:
    """All 8 figures explicit, 2dp strings, plus the GAP-099 per-component
    payment state — exact dict equality also pins that no keys beyond the
    agreed contract ride along."""
    _funded_booking(booking)

    payload = build_booking_payload(booking)

    assert payload["financials"] == {
        "total_gross": "10000.00",
        "total_net": "6960.00",
        "gross_deposit": "3000.00",
        "net_deposit": "2088.00",
        "deposit_commission": "522.00",
        "gross_balance": "7000.00",
        "net_balance": "4872.00",
        "balance_commission": "1218.00",
        "deposit_status": "pending",
        "deposit_due_at": None,
        "balance_status": "pending",
        "balance_due_at": None,
    }


def test_payload_financials_includes_charge_overlay(booking: Booking) -> None:
    """Manual charge lines move the booking-level pair through the GAP-076
    overlay — the non-proportionality that is the whole reason res sends
    every figure. A non-commissionable line passes through to the owner
    verbatim (gross and net +500, commission untouched); the schedule stays
    3000/7000, so the component figures don't move — exactly the shape a
    Zoho-side pro-rata formula could never reproduce."""
    _funded_booking(booking, noncomm_charge="500.00")

    payload = build_booking_payload(booking)

    assert payload["financials"] == {
        "total_gross": "10500.00",
        "total_net": "7460.00",
        "gross_deposit": "3000.00",
        "net_deposit": "2088.00",
        "deposit_commission": "522.00",
        "gross_balance": "7000.00",
        "net_balance": "4872.00",
        "balance_commission": "1218.00",
        "deposit_status": "pending",
        "deposit_due_at": None,
        "balance_status": "pending",
        "balance_due_at": None,
    }


def test_payload_financials_agrees_with_split_authority(booking: Booking) -> None:
    """Byte-agreement with the FinanceTab authority (the acceptance
    criterion), plus the conservation the authority guarantees: commission
    is conserved unconditionally whenever gross is scheduled; gross/net sum
    because this fixture's schedule equals the booking total (a fixture
    property, not a service guarantee — see owner_finance docstring)."""
    from reservations.services.owner_finance import (
        owner_money_for_booking,
        payment_component_splits,
    )

    _funded_booking(booking)

    payload = build_booking_payload(booking)

    financials = payload["financials"]
    money = owner_money_for_booking(booking)
    assert money is not None
    splits = {s["purpose"]: s for s in payment_component_splits(booking, money=money) or []}
    assert financials["total_gross"] == f"{money['gross_total']:.2f}"
    assert financials["total_net"] == f"{money['net_to_owner']:.2f}"
    assert financials["gross_deposit"] == f"{splits['deposit']['gross']:.2f}"
    assert financials["net_deposit"] == f"{splits['deposit']['net_to_owner']:.2f}"
    assert financials["deposit_commission"] == f"{splits['deposit']['commission']:.2f}"
    assert financials["gross_balance"] == f"{splits['balance']['gross']:.2f}"
    assert financials["net_balance"] == f"{splits['balance']['net_to_owner']:.2f}"
    assert financials["balance_commission"] == f"{splits['balance']['commission']:.2f}"
    # GAP-099: payment state is the authority's too — same latest-row status,
    # same earliest-scheduled due_at, ISO-rendered.
    assert financials["deposit_status"] == splits["deposit"]["status"]
    assert financials["deposit_due_at"] == _iso(splits["deposit"]["due_at"])
    assert financials["balance_status"] == splits["balance"]["status"]
    assert financials["balance_due_at"] == _iso(splits["balance"]["due_at"])
    # Conservation: commission unconditional, gross/net fixture-conditional.
    for total_key, part_keys in [
        ("total_gross", ("gross_deposit", "gross_balance")),
        ("total_net", ("net_deposit", "net_balance")),
    ]:
        assert Decimal(financials[total_key]) == sum(Decimal(financials[k]) for k in part_keys)
    assert money["commission"] == sum(
        Decimal(financials[k]) for k in ("deposit_commission", "balance_commission")
    )


def test_payload_financials_sparse_snapshot_is_all_null(booking: Booking) -> None:
    """Imported bookings carry `{}` snapshots — no owner money. Degrade
    explicitly: keys present, values null, never invented zeros (the
    GAP-082 placeholder posture, now per-figure)."""
    assert booking.pricing_snapshot == {}  # the fixture IS the sparse case

    payload = build_booking_payload(booking)

    financials = payload["financials"]
    assert set(financials) == FINANCIALS_KEYS
    assert all(value is None for value in financials.values())


def test_payload_financials_no_schedule_degrades_components_to_null(
    booking: Booking,
) -> None:
    """Owner money but no deposit/balance rows (financeless property):
    booking-level pair populated, the six component figures null."""
    _set_snapshot(booking, FINANCIALS_SNAPSHOT)

    payload = build_booking_payload(booking)

    financials = payload["financials"]
    assert set(financials) == FINANCIALS_KEYS
    assert financials["total_gross"] == "10000.00"
    assert financials["total_net"] == "6960.00"
    assert all(financials[key] is None for key in FINANCIALS_KEYS - {"total_gross", "total_net"})


# --- cancelled bookings keep their money (GAP-085) ------------------------
#
# Call decision: a cancelled booking pushes `status=cancelled` and leaves the
# figures for reporting. These tests stop a future "helpful" zero-on-cancel
# regression (the builder has no status gate — that absence is the contract).


def test_payload_cancelled_booking_keeps_full_financials(booking: Booking) -> None:
    """Settled money survives cancellation untouched — the close-money
    receiver only terminates unpaid PENDING rows."""
    _set_snapshot(booking, {**FINANCIALS_SNAPSHOT, "extras": [SNAPSHOT_EXTRAS[0]]})
    _payment(booking, purpose="deposit", amount="3000.00", status="succeeded")
    _payment(booking, purpose="balance", amount="7000.00", status="succeeded")
    booking.cancel("Guest illness")

    payload = build_booking_payload(booking)

    assert payload["status"] == BookingStatus.CANCELLED.value
    assert payload["cancel_reason"] == "Guest illness"
    assert payload["financials"] == {
        "total_gross": "10000.00",
        "total_net": "6960.00",
        "gross_deposit": "3000.00",
        "net_deposit": "2088.00",
        "deposit_commission": "522.00",
        "gross_balance": "7000.00",
        "net_balance": "4872.00",
        "balance_commission": "1218.00",
        "deposit_status": "succeeded",
        "deposit_due_at": None,
        "balance_status": "succeeded",
        "balance_due_at": None,
    }
    assert payload["extras"] == [
        {"label": "Heated pool", "amount": "350.00", "commissionable": True, "category": "heating"}
    ]


def test_payload_cancelled_with_pending_schedule_pushes_authority_zeros(
    booking: Booking,
) -> None:
    """Cancel terminates unpaid PENDING rows, so the splits authority — and
    FinanceTab — report 0.00 components; the push agrees byte-for-byte
    rather than inventing pre-cancellation figures. The booking-level pair
    still carries the money for reporting. Semantics flagged for the
    2026-08-12 Limitless call (see ticket close-out).

    GAP-099 / CHECK-004 item 3: this is exactly the case where Limitless'
    `status != "awaiting_deposit"` inference marked the deposit as received.
    The payload now says `deposit_status: cancelled` — a fact, not a guess."""
    _funded_booking(booking)
    booking.cancel("Change of plans")

    payload = build_booking_payload(booking)

    assert payload["financials"] == {
        "total_gross": "10000.00",
        "total_net": "6960.00",
        "gross_deposit": "0.00",
        "net_deposit": "0.00",
        "deposit_commission": "0.00",
        "gross_balance": "0.00",
        "net_balance": "0.00",
        "balance_commission": "0.00",
        "deposit_status": "cancelled",
        "deposit_due_at": None,
        "balance_status": "cancelled",
        "balance_due_at": None,
    }


# --- per-component payment state (GAP-099) --------------------------------
#
# The eight amounts say nothing about whether the deposit has been PAID;
# Limitless inferred it from BookingStatus and got it wrong (CHECK-004 item 3).
# Ship the split authority's `status` (latest schedule row, raw PaymentStatus)
# and `due_at` (earliest scheduled, ISO-8601) per component — facts, not
# derivations, null-degrading like every other figure in the block.


def test_payload_financials_component_statuses_paid_deposit_pending_balance(
    booking: Booking,
) -> None:
    """The headline case: deposit collected, balance outstanding — each
    component reports its own raw PaymentStatus."""
    _set_snapshot(booking, FINANCIALS_SNAPSHOT)
    _payment(booking, purpose="deposit", amount="3000.00", status="succeeded")
    _payment(booking, purpose="balance", amount="7000.00", status="pending")

    financials = build_booking_payload(booking)["financials"]

    assert financials["deposit_status"] == "succeeded"
    assert financials["balance_status"] == "pending"


def test_payload_financials_status_is_latest_row_not_failed_predecessor(
    booking: Booking,
) -> None:
    """A FAILED deposit superseded by a fresh PENDING re-collection reports
    the LATEST row (the authority's rule) — and the amount follows the same
    row, so both facts describe the live schedule, not history."""
    _set_snapshot(booking, FINANCIALS_SNAPSHOT)
    _payment(booking, purpose="deposit", amount="3000.00", status="failed")
    _payment(booking, purpose="deposit", amount="2500.00", status="pending")

    financials = build_booking_payload(booking)["financials"]

    assert financials["deposit_status"] == "pending"
    assert financials["gross_deposit"] == "2500.00"


def test_payload_financials_deposit_cancelled_on_live_booking(booking: Booking) -> None:
    """BUG-022: a zero deposit override cancels the PENDING deposit row —
    Zoho then reads `deposit_status: "cancelled"` with a null due date and
    0.00 deposit figures. BUG-026: the booking itself no longer strands in
    `awaiting_deposit` when that happens — the same resync call now advances
    it to `deposit_paid`. Pins the documented meaning of `cancelled`."""
    from payments.services import PaymentScheduler
    from properties.models.finance import PropertyFinance

    PropertyFinance.objects.get_or_create(property=booking.property)
    _funded_booking(booking)
    Booking.objects.filter(pk=booking.pk).update(
        status=BookingStatus.AWAITING_DEPOSIT.value, deposit_override_amount=Decimal("0")
    )
    fresh = Booking.objects.get(pk=booking.pk)
    PaymentScheduler.resync_for_booking(fresh)

    financials = build_booking_payload(fresh)["financials"]

    fresh.refresh_from_db()
    assert fresh.status == BookingStatus.DEPOSIT_PAID.value
    assert financials["deposit_status"] == "cancelled"
    assert financials["deposit_due_at"] is None
    assert financials["gross_deposit"] == "0.00"
    assert financials["balance_status"] == "pending"


def test_payload_financials_component_due_at_is_iso_or_null(booking: Booking) -> None:
    """`due_at` is ISO-8601 when scheduled, null when not — and the whole
    payload still JSON-serialises (the round-trip test's fixture sets no
    due_at, so a raw datetime leaking through would otherwise stay green)."""
    due = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    _set_snapshot(booking, FINANCIALS_SNAPSHOT)
    _payment(booking, purpose="deposit", amount="3000.00", due_at=due)
    _payment(booking, purpose="balance", amount="7000.00")

    payload = build_booking_payload(booking)

    financials = payload["financials"]
    assert financials["deposit_due_at"] == due.isoformat()
    assert financials["balance_due_at"] is None
    json.dumps(payload)


# --- extras (GAP-085) -----------------------------------------------------
#
# Itemized separately per the 2026-07-29 call, commissionable flags included.
# `category` carries the GAP-088 taxonomy: snapshot extras pass their stored
# `ExtraKind` through (sanitized — an unfenced/garbage kind degrades to
# null), manual charge lines send `BookingChargeItem.category`. Two sources:
# the engine-applied pricing extras inside the snapshot, then manual
# BookingChargeItem lines. Purely informational — both already sit inside
# total_gross (snapshot total / charge overlay); Zoho must not re-add them.

# Fixture simplification: a real engine snapshot's `total` already includes
# its extras; these tests graft `extras` on without recomputing the worked
# example because the money authority ignores the key — the extras list is
# informational, never additive.
SNAPSHOT_EXTRAS = [
    {
        "extra_id": 7,
        "name": "Heated pool",
        "kind": "heating",
        "calc": "fixed",
        "computed_amount": "350.00",
        "commissionable": True,
    },
    {
        "extra_id": 9,
        "name": "Chef (pass-through)",
        "kind": "service_fee",
        "calc": "fixed",
        "computed_amount": "900.00",
        "commissionable": False,
    },
]


def test_payload_extras_itemizes_engine_snapshot_extras(booking: Booking) -> None:
    _set_snapshot(booking, {**FINANCIALS_SNAPSHOT, "extras": SNAPSHOT_EXTRAS})

    payload = build_booking_payload(booking)

    assert payload["extras"] == [
        {"label": "Heated pool", "amount": "350.00", "commissionable": True, "category": "heating"},
        {
            "label": "Chef (pass-through)",
            "amount": "900.00",
            "commissionable": False,
            "category": "service_fee",
        },
    ]


def test_payload_extras_appends_manual_charge_items(booking: Booking) -> None:
    """Manual lines after engine extras; signed amounts survive verbatim —
    a negative line is a credit, not a data error."""
    _set_snapshot(booking, {**FINANCIALS_SNAPSHOT, "extras": [SNAPSHOT_EXTRAS[0]]})
    _charge(
        booking,
        label="Late checkout",
        amount="120.00",
        commissionable=True,
        category="service_fee",
    )
    _charge(booking, label="Negotiated rate adjustment", amount="-150.00", commissionable=True)

    payload = build_booking_payload(booking)

    assert payload["extras"] == [
        {"label": "Heated pool", "amount": "350.00", "commissionable": True, "category": "heating"},
        {
            "label": "Late checkout",
            "amount": "120.00",
            "commissionable": True,
            "category": "service_fee",
        },
        {
            "label": "Negotiated rate adjustment",
            "amount": "-150.00",
            "commissionable": True,
            "category": "other",
        },
    ]


def test_payload_extras_sanitizes_unknown_snapshot_kind_to_null(booking: Booking) -> None:
    """Manual-override snapshot writes are unfenced — a kind outside the
    ChargeCategory vocabulary (or a missing key) degrades to null rather than
    leaking a second vocabulary into Zoho. The gate is ChargeCategory, not
    ExtraKind: a charge-only value like `damage` passes through."""
    _set_snapshot(
        booking,
        {
            **FINANCIALS_SNAPSHOT,
            "extras": [
                {**SNAPSHOT_EXTRAS[0], "kind": "Final Clean!!"},
                {k: v for k, v in SNAPSHOT_EXTRAS[1].items() if k != "kind"},
                {**SNAPSHOT_EXTRAS[0], "kind": "damage"},
            ],
        },
    )

    payload = build_booking_payload(booking)

    assert [e["category"] for e in payload["extras"]] == [None, None, "damage"]


def test_payload_extras_empty_when_sparse_and_unchargeed(booking: Booking) -> None:
    """Imported `{}` snapshots have no `extras` key at all — the builder must
    not KeyError, and an extras-less booking sends an empty list, not null
    (the list itself is always computable)."""
    assert booking.pricing_snapshot == {}

    payload = build_booking_payload(booking)

    assert payload["extras"] == []


def test_payload_anonymized_person_fails_closed(booking: Booking) -> None:
    booking.person.anonymize()
    booking.refresh_from_db()

    payload = build_booking_payload(booking)

    assert payload["person"] is None
    assert "[REDACTED]" not in json.dumps(payload)


def test_payload_json_round_trips(booking: Booking) -> None:
    # Funded with a snapshot extra AND a charge item: a Decimal leaking into
    # the financials block or either extras source must fail here.
    _funded_booking(
        booking,
        noncomm_charge="500.00",
        snapshot={**FINANCIALS_SNAPSHOT, "extras": [SNAPSHOT_EXTRAS[0]]},
    )
    payload = build_booking_payload(booking)
    assert json.loads(json.dumps(payload)) == payload


def test_payload_query_count_pinned(booking: Booking) -> None:
    """One SELECT via the select_related chain + 6 prefetch buckets
    (person/agent emails+phones, payments, charge_items) — dropping a leg
    regresses to lazy walks. Funded WITH a charge item so the financials
    block runs its full overlay path: dropping the `with_charges_total`
    annotations (per-call aggregate fallback) or the `property__finance`
    select_related leg each cost an extra query and fail the pin."""
    booking.agent = cast("Person", PersonFactory())
    booking.save()
    _funded_booking(booking, noncomm_charge="500.00")

    with assert_max_queries(7):
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


@pytest.mark.usefixtures("run_on_commit_immediately")
def test_charge_item_added_bumps(booking: Booking, delay_mock: mock.Mock) -> None:
    """BUG-021: a charge item moves the total via `booking_total_changed`
    (never `Booking.save()`) — the resync receiver must re-push."""
    with override_settings(ZOHO_FLOW_WEBHOOKS=WEBHOOKS):
        enqueue_zoho_push(booking)
        record = _record_for(booking)
        _mark_in_sync(record)
        delay_mock.reset_mock()

        _charge(booking, label="Chef pass-through", amount="500.00", commissionable=False)

    record.refresh_from_db()
    assert record.status == SyncStatus.PENDING
    assert delay_mock.call_count == 1


@pytest.mark.usefixtures("run_on_commit_immediately")
def test_charge_item_deleted_bumps(booking: Booking, delay_mock: mock.Mock) -> None:
    """Same seam via `post_delete` — deleting a charge item also moves the
    total and must re-push."""
    from reservations.models import BookingChargeItem

    with override_settings(ZOHO_FLOW_WEBHOOKS=WEBHOOKS):
        _charge(booking, label="Chef pass-through", amount="500.00", commissionable=False)
        record = _record_for(booking)
        _mark_in_sync(record)

        BookingChargeItem.objects.get(booking=booking).delete()

    record.refresh_from_db()
    assert record.status == SyncStatus.PENDING


@pytest.mark.usefixtures("run_on_commit_immediately")
def test_deposit_settle_bumps_even_when_booking_already_advanced(
    booking: Booking, delay_mock: mock.Mock
) -> None:
    """BUG-021: real money settling while `record_deposit` is swallowed as an
    `InvalidTransition` (seeding-order double-advance, mirrors
    payments/tests/test_booking_advance_receiver.py
    ::test_settlement_with_booking_already_advanced_is_idempotent_skip) must
    still re-push — the payment state genuinely changed."""
    with override_settings(ZOHO_FLOW_WEBHOOKS=WEBHOOKS):
        booking.record_deposit()
        record = _record_for(booking)
        _mark_in_sync(record)

        payment = _payment(booking, purpose="deposit", amount="3000.00")
        payment.mark_paid(payment.amount, timezone.now(), "bank_transfer", "BT-REF-1")

    record.refresh_from_db()
    assert record.status == SyncStatus.PENDING


@pytest.mark.usefixtures("run_on_commit_immediately")
def test_deposit_failed_bumps(booking: Booking, delay_mock: mock.Mock) -> None:
    """BUG-021: a schedule-row payment reaching FAILED changes `deposit_status`
    in the Zoho financials block (GAP-099) but advances nothing — the ticket's
    own fix sketch names 'Payment post_save for status changes on schedule
    rows', not just settled/waived, so a failure must re-push too."""
    with override_settings(ZOHO_FLOW_WEBHOOKS=WEBHOOKS):
        enqueue_zoho_push(booking)
        record = _record_for(booking)
        _mark_in_sync(record)

        payment = _payment(booking, purpose="deposit", amount="3000.00")
        payment.transition_to("failed")

    record.refresh_from_db()
    assert record.status == SyncStatus.PENDING
