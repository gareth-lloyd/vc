"""Dashboard-activity contract: after *any* `seed_dev` run the staff
dashboard's today-anchored tiles (arrivals today, check-outs today, new
enquiries, awaiting balance) and the owner portal's upcoming-arrivals table
must all be non-empty — the dense calendar alone almost never lands a stay
exactly on today, never rests a booking at AWAITING_BALANCE, and never leaves
an enquiry NEW.

These run against an isolated transactional DB (no accumulation from other
tests), so per-run counts can be asserted directly.
"""

from __future__ import annotations

from datetime import date, timedelta
from io import StringIO

import pytest
from django.core.management import call_command

from reservations.enums import BookingStatus, EnquiryStatus
from reservations.models.booking import Booking
from reservations.models.enquiry import Enquiry
from seeding.context import utc_today

# Statuses the owner dashboard excludes from its upcoming-arrivals table
# (mirrors `_NON_COUNTING` in reservations/views/owner.py).
_OWNER_NON_COUNTING = (
    BookingStatus.DRAFT.value,
    BookingStatus.CANCELLED.value,
    BookingStatus.EXPIRED.value,
    BookingStatus.DECLINED.value,
)


def _seed(
    profile: str, *, properties: int, bookings: int, seed: int, dashboard: bool = True
) -> None:
    args = [
        "--properties",
        str(properties),
        "--bookings",
        str(bookings),
        "--profile",
        profile,
        "--seed",
        str(seed),
    ]
    if not dashboard:
        args.append("--no-dashboard-activity")
    call_command("seed_dev", *args, stdout=StringIO())


def _assert_staff_dashboard_populated(today: date) -> None:
    """The four structurally-dead staff tiles, at the small-scale (x1) floor."""
    arrivals = Booking.objects.filter(
        date_from=today, status=BookingStatus.BALANCE_PAID.value
    ).count()
    assert arrivals >= 5, f"expected ≥5 arrivals today, got {arrivals}"

    # Departures rest BALANCE_PAID, not CHECKED_IN — the auto_check_out beat
    # task sweeps CHECKED_IN stays with date_to <= today into terminal
    # CHECKED_OUT, which the dashboard's exclude_terminal filter hides.
    departures = Booking.objects.filter(
        date_to=today, status=BookingStatus.BALANCE_PAID.value
    ).count()
    assert departures >= 3, f"expected ≥3 check-outs today, got {departures}"

    awaiting = Booking.objects.filter(status=BookingStatus.AWAITING_BALANCE.value).count()
    assert awaiting >= 4, f"expected ≥4 awaiting-balance bookings, got {awaiting}"

    new = Enquiry.objects.filter(status=EnquiryStatus.NEW.value).count()
    assert new >= 5, f"expected ≥5 NEW enquiries, got {new}"


@pytest.mark.django_db(transaction=True)
def test_happy_seed_populates_staff_dashboard() -> None:
    """Even the minimal legacy-shaped profile must light the dashboard up."""
    _seed("happy", properties=5, bookings=8, seed=42)
    _assert_staff_dashboard_populated(utc_today())


@pytest.mark.django_db(transaction=True)
def test_mixed_seed_populates_both_dashboards() -> None:
    """One mixed run backing both surfaces: the staff tiles survive collision
    handling against the dense calendar + operator blocks, and the owner
    portal's 30-day upcoming-arrivals window has rows on granted villas."""
    from owners.models import OwnerOrgProperty

    _seed("mixed", properties=5, bookings=30, seed=42)
    today = utc_today()

    _assert_staff_dashboard_populated(today)

    granted = list(
        OwnerOrgProperty.objects.filter(
            organisation__name="Kostas Hospitality Ltd", end_date__isnull=True
        ).values_list("property_id", flat=True)
    )
    assert granted, "owner_orgs stage should have granted villas"
    upcoming = (
        Booking.objects.filter(
            property_id__in=granted,
            date_from__gt=today,
            date_from__lte=today + timedelta(days=30),
        )
        .exclude(status__in=_OWNER_NON_COUNTING)
        .count()
    )
    assert upcoming >= 3, f"expected ≥3 owner upcoming arrivals, got {upcoming}"


@pytest.mark.django_db(transaction=True)
def test_dashboard_activity_is_additive_on_rerun() -> None:
    """A second run appends more today-activity without colliding on the
    no-overlap constraint (new stays slot into gaps or mint showcase villas)."""
    _seed("happy", properties=4, bookings=6, seed=1)
    today = utc_today()
    first = Booking.objects.filter(date_from=today).count()
    assert first > 0
    _seed("happy", properties=4, bookings=6, seed=2)
    assert Booking.objects.filter(date_from=today).count() > first


@pytest.mark.django_db(transaction=True)
def test_no_dashboard_activity_flag_disables_stage() -> None:
    """`--no-dashboard-activity` restores the exact legacy output — no
    today-anchored stays, no NEW enquiries — for exact-count consumers."""
    _seed("happy", properties=4, bookings=6, seed=42, dashboard=False)
    today = utc_today()
    assert Booking.objects.filter(date_from=today).count() == 0
    assert Booking.objects.filter(date_to=today).count() == 0
    assert Booking.objects.filter(status=BookingStatus.AWAITING_BALANCE.value).count() == 0
    assert Enquiry.objects.filter(status=EnquiryStatus.NEW.value).count() == 0
