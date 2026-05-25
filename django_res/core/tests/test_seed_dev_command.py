"""End-to-end coherence test for the seed_dev command.

Split by profile:

* `--profile happy` reproduces the pre-v2 uniform success-path graph and
  remains the deterministic floor every other profile builds on.
* `--profile mixed` (default) adds quotation lifecycle, pre-approval,
  expired/declined bookings, concierge, refunds, guest preferences, repeat
  guests, and a property-status spread — verified in aggregate, not row by
  row, since the dials are stochastic.
"""

from __future__ import annotations

from datetime import date
from io import StringIO

import pytest
from django.core.management import call_command

from payments.enums import RefundStatus
from payments.models.payment import Payment
from payments.models.refund import Refund
from properties.enums import PropertyStatus
from properties.models import Property
from reservations.enums import (
    BookingStatus,
    ConciergeStatus,
    EnquiryStatus,
    QuotationStatus,
)
from reservations.models.booking import Booking, BookingEvent
from reservations.models.concierge import BookingConciergeItem
from reservations.models.enquiry import Enquiry
from reservations.models.preferences import GuestPreference
from reservations.models.quotation import Quotation

pytestmark = pytest.mark.django_db


def _run(
    properties: int = 2,
    bookings: int = 3,
    profile: str = "happy",
    seed: int = 1,
) -> None:
    call_command(
        "seed_dev",
        "--properties",
        str(properties),
        "--bookings",
        str(bookings),
        "--profile",
        profile,
        "--seed",
        str(seed),
        stdout=StringIO(),
    )


# ---------------------------------------------------------------------------
# Profile: happy (the deterministic baseline)
# ---------------------------------------------------------------------------
def test_seed_dev_happy_builds_a_coherent_graph() -> None:
    # 3 bookings span tracks 0/1/2 -> AWAITING_DEPOSIT/DEPOSIT_PAID/BALANCE_PAID,
    # enough to assert the status spread without the full preset's cost.
    _run()

    prop = Property.objects.filter(rate_plans__isnull=False).first()
    assert prop is not None
    # The 1:1 children the booking/pricing services walk.
    assert prop.location is not None
    assert prop.capacity is not None
    assert prop.finance is not None
    assert prop.hero_image() is not None

    booking = Booking.objects.select_related("quotation_line").first()
    assert booking is not None
    assert BookingEvent.objects.filter(booking=booking).exists()
    assert Quotation.objects.exists()
    assert Payment.objects.filter(booking=booking).exists()

    # Happy profile drives quotations through SENT → ACCEPTED before opening
    # the booking — never leaves them in DRAFT.
    assert not Quotation.objects.filter(status=QuotationStatus.DRAFT.value).exists()

    # Status spread: not every booking sits in one bucket.
    statuses = set(Booking.objects.values_list("status", flat=True))
    assert len(statuses) > 1

    # Happy profile: no pre-approval, no expired, no concierge, no refunds.
    assert not Booking.objects.filter(status=BookingStatus.PENDING_OWNER_APPROVAL.value).exists()
    assert not Booking.objects.filter(status=BookingStatus.EXPIRED.value).exists()
    assert not Booking.objects.filter(status=BookingStatus.DECLINED.value).exists()
    assert not BookingConciergeItem.objects.exists()
    assert not Refund.objects.exists()
    assert not GuestPreference.objects.exists()


def test_seed_dev_happy_is_additive_on_rerun() -> None:
    _run(properties=1, bookings=1)
    first = Booking.objects.count()
    _run(properties=1, bookings=1)
    assert Booking.objects.count() > first  # appended, no unique-constraint error


# ---------------------------------------------------------------------------
# Profile: mixed (the new default — "interesting" data)
# ---------------------------------------------------------------------------
def test_seed_dev_mixed_emits_quotation_lifecycle_variety() -> None:
    # Bigger run so the percentage-based knobs actually emit each bucket.
    _run(properties=8, bookings=24, profile="mixed", seed=42)

    statuses = set(Quotation.objects.values_list("status", flat=True))
    # Booking-bound quotations land on ACCEPTED; the extra_quotations stage
    # produces a slice of SENT / EXPIRED / CANCELLED. DRAFT is no longer
    # observable — the seeder always drives them past it.
    assert QuotationStatus.ACCEPTED.value in statuses
    assert (
        len(
            statuses
            & {
                QuotationStatus.SENT.value,
                QuotationStatus.EXPIRED.value,
                QuotationStatus.CANCELLED.value,
            }
        )
        >= 1
    )
    assert QuotationStatus.DRAFT.value not in statuses


def test_seed_dev_mixed_drives_pre_approval_path() -> None:
    _run(properties=8, bookings=24, profile="mixed", seed=42)

    # At least one booking has touched the PENDING_OWNER_APPROVAL state
    # (either still there, or transitioned to DECLINED / AWAITING_DEPOSIT
    # after owner_approve).
    pre_approval_events = BookingEvent.objects.filter(
        to_status=BookingStatus.PENDING_OWNER_APPROVAL.value
    )
    assert pre_approval_events.exists()


def test_seed_dev_mixed_emits_enquiry_status_spread() -> None:
    _run(properties=8, bookings=24, profile="mixed", seed=42)

    statuses = set(Enquiry.objects.values_list("status", flat=True))
    # The booking-path enquiries hit CONVERTED; orphan enquiries surface
    # LOST + CONTACTED; quotation-only enquiries hit QUOTED.
    assert EnquiryStatus.CONVERTED.value in statuses
    expected_others = {
        EnquiryStatus.QUOTED.value,
        EnquiryStatus.CONTACTED.value,
        EnquiryStatus.LOST.value,
    }
    assert statuses & expected_others, f"expected at least one of {expected_others} in {statuses}"


def test_seed_dev_mixed_attaches_concierge_items() -> None:
    _run(properties=8, bookings=24, profile="mixed", seed=42)

    assert BookingConciergeItem.objects.exists()
    statuses = set(BookingConciergeItem.objects.values_list("status", flat=True))
    realistic = {
        ConciergeStatus.REQUESTED.value,
        ConciergeStatus.CONFIRMED.value,
        ConciergeStatus.DELIVERED.value,
        ConciergeStatus.CANCELLED.value,
    }
    assert statuses & realistic


def test_seed_dev_mixed_emits_refund_lifecycle() -> None:
    _run(properties=8, bookings=24, profile="mixed", seed=42)

    assert Refund.objects.exists()
    statuses = set(Refund.objects.values_list("status", flat=True))
    realistic = {
        RefundStatus.PENDING.value,
        RefundStatus.APPROVED.value,
        RefundStatus.REJECTED.value,
        RefundStatus.EXECUTING.value,
        RefundStatus.SUCCEEDED.value,
        RefundStatus.FAILED.value,
    }
    assert len(statuses & realistic) >= 2


def test_seed_dev_mixed_attaches_guest_preferences() -> None:
    _run(properties=8, bookings=24, profile="mixed", seed=42)

    assert GuestPreference.objects.exists()


def test_seed_dev_mixed_spreads_property_status() -> None:
    _run(properties=10, bookings=4, profile="mixed", seed=42)

    statuses = set(Property.objects.values_list("status", flat=True))
    assert PropertyStatus.ACTIVE.value in statuses
    # Knobs sit ~5% each at mixed; with 10 properties + the +1 floor we
    # always get at least one of DRAFT / ARCHIVED.
    assert PropertyStatus.DRAFT.value in statuses or PropertyStatus.ARCHIVED.value in statuses


def test_seed_dev_mixed_spreads_booking_dates_around_today() -> None:
    """The temporal-spread knob should produce bookings on both sides of
    today, so dashboards see arrivals/departures every day of the dev week."""
    _run(properties=8, bookings=24, profile="mixed", seed=42)

    today = date.today()
    earliest = Booking.objects.order_by("date_from").values_list("date_from", flat=True).first()
    latest = Booking.objects.order_by("-date_from").values_list("date_from", flat=True).first()
    assert earliest is not None and latest is not None
    assert earliest < today
    assert latest > today
