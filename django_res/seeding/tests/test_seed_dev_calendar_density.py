"""Calendar-density contract: `seed_dev` (mixed/chaos) must populate property
availability calendars densely but with realistic *variety* — a few packed
villas, several busy, many light, and some empty — and exercise the reachable
cell states (incl. the AM/PM changeover split) so the availability tab has real
data to render. `happy` stays sparse with no changeover.

These run against an isolated transactional DB (no accumulation from other
tests), so the per-run distribution can be asserted directly.
"""

from __future__ import annotations

from datetime import date, timedelta
from io import StringIO

import pytest
from django.core.management import call_command

from properties.models import Property
from reservations.services.availability import AvailabilityService, CellStatus

_WINDOW = timedelta(days=365)


def _seed(profile: str, *, properties: int, bookings: int, seed: int) -> None:
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


def _booked_days(prop: Property, today: date) -> int:
    """Days a stay occupies the calendar (reason ``booked``). Excludes
    quotation/operator-block holds, so empty-tier villas read as 0 even when
    they pick up a stray quotation cell."""
    cal = AvailabilityService.calendar(prop, today - _WINDOW, today + _WINDOW)
    return sum(1 for cell in cal.values() if cell.reason == "booked")


def _calendars(today: date) -> dict[int, dict[date, CellStatus]]:
    return {
        p.pk: AvailabilityService.calendar(p, today - _WINDOW, today + _WINDOW)
        for p in Property.objects.filter(status="active")
    }


@pytest.mark.django_db(transaction=True)
def test_seed_dev_mixed_calendar_is_dense_varied_and_current() -> None:
    """One mixed portfolio asserted from every density angle.

    `seed_dev` is deterministic at a fixed seed, so a single
    `--properties 10 --bookings 60 --seed 42` run backs all of these checks —
    each was previously its own identically-seeded test, and each `transaction=True`
    run flushes + reseeds the whole DB, so collapsing them is a large wall-clock win:

    * a varied density gradient (≥1 packed villa, a lighter tail, ≥2 empty);
    * a back-to-back AM/PM changeover day, falling today or later;
    * occupancy inside the current month.
    """
    _seed("mixed", properties=10, bookings=60, seed=42)
    today = date.today()

    # ---- Varied density: ≥1 packed villa, a lighter tail, ≥2 empty ----
    # Empty villas double as property_lifecycle fodder (may end up
    # DRAFT/ARCHIVED), so count occupancy across every status, not just active.
    booked = sorted(_booked_days(p, today) for p in Property.objects.all())
    packed = [n for n in booked if n >= 40]
    empty = [n for n in booked if n == 0]
    stay_bearing = [n for n in booked if n > 0]
    assert packed, f"expected at least one packed villa, booked_days={booked}"
    assert len(empty) >= 2, f"expected ≥2 empty villas, booked_days={booked}"
    # Clear density gradient: the lightest stay-bearing villa is far lighter
    # than the busiest, not a flat uniform stamp.
    assert stay_bearing[0] * 2 <= stay_bearing[-1], booked
    # A packed villa is busy, not wall-to-wall: gaps keep it bookable.
    assert max(booked) < 2 * _WINDOW.days, "a villa should never be fully booked"

    # ---- Changeover: ≥1 AM/PM segment cell, all today-or-later ----
    # Needs both adjacent stays non-terminal and check-in/out times set; forced
    # changeover pairs never pay a deposit, so a past changeover day would be an
    # AWAITING_DEPOSIT stay production never reaches.
    calendars = _calendars(today)
    changeover_days = [
        day for cal in calendars.values() for day, cell in cal.items() if cell.segments
    ]
    assert changeover_days, "expected at least one AM/PM changeover cell"
    assert min(changeover_days) >= today, (
        f"changeover days must be today-or-later, earliest was {min(changeover_days)}"
    )

    # ---- Current-month occupancy: the availability tab opens on this month ----
    month = today + timedelta(days=30)
    occupied_now = any(
        not cell.available
        for cal in calendars.values()
        for day, cell in cal.items()
        if today <= day < month
    )
    assert occupied_now, "expected current-month occupancy on at least one villa"


@pytest.mark.django_db(transaction=True)
def test_seed_dev_dense_two_properties_still_books() -> None:
    """A tiny portfolio must still honour `--bookings`. The empty-tier floor is
    capped at `n - 1`, so `--properties 2` leaves one stay-bearing villa instead
    of consuming the whole portfolio and silently producing zero bookings."""
    from reservations.models.booking import Booking

    _seed("mixed", properties=2, bookings=10, seed=7)
    assert Booking.objects.count() == 10


@pytest.mark.django_db(transaction=True)
def test_seed_dev_mixed_covers_reachable_cell_states() -> None:
    """Aggregate over the portfolio the calendar exercises every reachable
    state."""
    _seed("mixed", properties=12, bookings=80, seed=42)
    today = date.today()
    reasons: set[str] = set()
    has_available = False
    for cal in _calendars(today).values():
        for cell in cal.values():
            if cell.available:
                has_available = True
            else:
                reasons.add(cell.reason)

    assert has_available, "every portfolio should have free days"
    # Bookings + open quotations are always produced.
    assert {"booked", "quotation"} <= reasons, reasons
    # Operator blocks land on a mix of villas; at least two of the three kinds
    # show up at this scale.
    block_kinds = {"owner_block", "maintenance", "manual"}
    assert len(reasons & block_kinds) >= 2, reasons


@pytest.mark.django_db(transaction=True)
def test_seed_dev_happy_stays_sparse_with_no_changeover() -> None:
    """The happy profile keeps the legacy shape: null changeover times (so no
    AM/PM split) and a thin round-robin calendar."""
    _seed("happy", properties=4, bookings=6, seed=42)
    today = date.today()
    for prop in Property.objects.filter(status="active"):
        assert prop.settings.check_in_time is None
        assert prop.settings.check_out_time is None
    has_changeover = any(
        cell.segments for cal in _calendars(today).values() for cell in cal.values()
    )
    assert not has_changeover, "happy profile must not produce changeover cells"


@pytest.mark.django_db(transaction=True)
def test_seed_dev_dense_is_additive_on_rerun() -> None:
    """A second dense run appends more bookings without colliding on holds or
    the no-overlap constraint."""
    from reservations.models.booking import Booking

    _seed("mixed", properties=6, bookings=30, seed=1)
    first = Booking.objects.count()
    assert first > 0
    _seed("mixed", properties=6, bookings=30, seed=2)
    assert Booking.objects.count() > first
