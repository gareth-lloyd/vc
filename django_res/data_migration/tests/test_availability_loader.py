"""AvailabilityBlockLoader: VillaAvailability future non-available runs ->
source-less MANUAL BookingHolds (one per coalesced per-property run)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

import pytest
from django.utils import timezone

from data_migration.base import LoadReport
from data_migration.loaders.availability import (
    AVAILABILITY_LEGACY_PREFIX,
    AvailabilityBlockLoader,
    coalesce_runs,
)
from reservations.enums import BookingHoldReason
from reservations.models.booking import Booking, BookingHold

if TYPE_CHECKING:
    from properties.models.property import Property


def _row(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "PropertyId": 900,
        "AvailableDate": datetime(2026, 7, 25),  # pyodbc yields datetimes
        "AvailableStatus": 50,
        "Notes": None,
        "CreatedBy": "admin",
    }
    base.update(overrides)
    return base


def _days(start: date, count: int, **overrides: Any) -> list[dict[str, Any]]:
    return [
        _row(
            AvailableDate=datetime.combine(start + timedelta(days=i), datetime.min.time()),
            **overrides,
        )
        for i in range(count)
    ]


# --- coalesce_runs (pure) ---


def test_coalesce_consecutive_days_into_one_run() -> None:
    runs = coalesce_runs(_days(date(2026, 7, 25), 3))
    assert len(runs) == 1
    assert (runs[0].start, runs[0].end) == (date(2026, 7, 25), date(2026, 7, 27))
    assert runs[0].status == 50
    assert runs[0].created_by == "admin"


def test_coalesce_splits_on_calendar_gap() -> None:
    rows = _days(date(2026, 7, 1), 2) + _days(date(2026, 7, 10), 2)
    runs = coalesce_runs(rows)
    assert [(r.start, r.end) for r in runs] == [
        (date(2026, 7, 1), date(2026, 7, 2)),
        (date(2026, 7, 10), date(2026, 7, 11)),
    ]


def test_coalesce_splits_on_status_change() -> None:
    rows = _days(date(2026, 7, 1), 2, AvailableStatus=30) + _days(
        date(2026, 7, 3), 2, AvailableStatus=50
    )
    runs = coalesce_runs(rows)
    assert [(r.start, r.status) for r in runs] == [
        (date(2026, 7, 1), 30),
        (date(2026, 7, 3), 50),
    ]


def test_coalesce_splits_on_property_change() -> None:
    rows = _days(date(2026, 7, 1), 2, PropertyId=900) + _days(date(2026, 7, 3), 2, PropertyId=901)
    runs = coalesce_runs(rows)
    assert [(r.property_id, r.start) for r in runs] == [
        (900, date(2026, 7, 1)),
        (901, date(2026, 7, 3)),
    ]


def test_coalesce_is_input_order_independent() -> None:
    rows = _days(date(2026, 7, 1), 3)
    assert coalesce_runs(list(reversed(rows))) == coalesce_runs(rows)


def test_coalesce_dedupes_duplicate_day_rows() -> None:
    # A dirty duplicate (property, day) row must merge into the run, not mint
    # a second run whose legacy_id would collide with the first's.
    rows = [*_days(date(2026, 7, 1), 2), _row(AvailableDate=datetime(2026, 7, 1))]
    runs = coalesce_runs(rows)
    assert len(runs) == 1
    assert (runs[0].start, runs[0].end) == (date(2026, 7, 1), date(2026, 7, 2))


def _dupe(
    status: int, *, row_id: int, created: datetime, updated: datetime | None
) -> dict[str, Any]:
    return _row(
        Id=row_id,
        AvailableDate=datetime(2026, 5, 23),
        AvailableStatus=status,
        CreatedAt=created,
        UpdatedAt=updated,
    )


@pytest.mark.parametrize("reverse", [False, True])
def test_coalesce_duplicate_day_keeps_the_latest_edit(reverse: bool) -> None:
    """BUG-029 §3: villa 3 / 2025-05-23 carries status 50 at 09:16 and 60 at
    09:27. Legacy updates rows in place (stamping UpdatedAt), so recency is
    COALESCE(UpdatedAt, CreatedAt) — not Id — and input order is irrelevant."""
    rows = [
        # Lower Id but edited last.
        _dupe(
            60, row_id=1, created=datetime(2025, 5, 1, 9, 0), updated=datetime(2025, 5, 23, 9, 27)
        ),
        _dupe(50, row_id=2, created=datetime(2025, 5, 23, 9, 16), updated=None),
    ]
    (run,) = coalesce_runs(list(reversed(rows)) if reverse else rows)
    assert run.status == 60


def test_coalesce_duplicate_day_same_stamp_breaks_tie_on_highest_id() -> None:
    stamp = datetime(2025, 5, 23, 9, 0)
    rows = [
        _dupe(50, row_id=8, created=stamp, updated=None),
        _dupe(60, row_id=3, created=stamp, updated=None),
    ]
    (run,) = coalesce_runs(rows)
    assert run.status == 50


def test_coalesce_newer_non_blocking_row_releases_the_day() -> None:
    # The scheduler's expired-hold release writes status 70 over an old hold:
    # the latest row wins BEFORE non-blocking statuses are dropped.
    rows = [
        _dupe(40, row_id=1, created=datetime(2025, 5, 1), updated=None),
        _dupe(70, row_id=2, created=datetime(2025, 5, 2), updated=None),
    ]
    assert coalesce_runs(rows) == []


def test_coalesce_drops_non_blocking_statuses() -> None:
    rows = [
        *_days(date(2026, 7, 1), 1, AvailableStatus=10),
        *_days(date(2026, 7, 2), 1, AvailableStatus=30),
        *_days(date(2026, 7, 3), 1, AvailableStatus=70),
    ]
    assert [(r.start, r.end, r.status) for r in coalesce_runs(rows)] == [
        (date(2026, 7, 2), date(2026, 7, 2), 30)
    ]


def test_coalesce_collects_distinct_day_notes_in_date_order() -> None:
    rows = _days(date(2026, 7, 1), 3)
    rows[0]["Notes"] = "owner away"
    rows[1]["Notes"] = "owner away"  # duplicate — collected once
    rows[2]["Notes"] = "back Monday"
    (run,) = coalesce_runs(rows)
    assert run.notes == ["owner away", "back Monday"]


def test_coalesce_drops_notes_that_echo_the_status_code() -> None:
    # Legacy stuffed the day's status code into Notes on most rows ("50" on a
    # Booked day) — pure noise, dropped; a real note is kept.
    rows = _days(date(2026, 7, 1), 2, AvailableStatus=50)
    rows[0]["Notes"] = "50"
    rows[1]["Notes"] = "confirmed"
    (run,) = coalesce_runs(rows)
    assert run.notes == ["confirmed"]


# --- loader (Postgres) ---


@pytest.mark.django_db
def test_run_loads_as_half_open_manual_hold(seeded: Property) -> None:
    """Inclusive grid days start..end land as `[start, end + 1 day)` — the
    half-open convention `BookingHold.live_overlapping` reads."""
    loader = AvailabilityBlockLoader()
    report = LoadReport(loader=loader.name)
    rows = _days(date(2026, 7, 25), 3)
    rows[0]["Notes"] = "owner refurb"

    loader._load_rows(rows, report)

    hold = BookingHold.objects.get(legacy_id__startswith=AVAILABILITY_LEGACY_PREFIX)
    assert report.created == 1
    assert hold.property == seeded
    assert (hold.date_from, hold.date_to) == (date(2026, 7, 25), date(2026, 7, 28))
    assert hold.reason == BookingHoldReason.MANUAL
    assert hold.expires_at is None and hold.released_at is None
    assert hold.quotation_id is None and hold.booking_id is None
    assert hold.legacy_id == "avail-900-2026-07-25"
    assert hold.notes == (
        "Imported from legacy availability (status Booked, created by admin)\nowner refurb"
    )


@pytest.mark.django_db
def test_write_failure_on_one_run_is_isolated(
    seeded: Property, monkeypatch: pytest.MonkeyPatch
) -> None:
    """BUG-029 §4: a write-time exception on one run is recorded against that
    run's legacy_id; the other runs still load."""
    real_create = BookingHold.objects.create

    def _create(**kwargs: Any) -> BookingHold:
        if kwargs["date_from"] == date(2026, 7, 1):
            raise RuntimeError("boom")
        return real_create(**kwargs)

    monkeypatch.setattr(BookingHold.objects, "create", _create)
    loader = AvailabilityBlockLoader()
    report = LoadReport(loader=loader.name)

    loader._load_rows(_days(date(2026, 7, 1), 2) + _days(date(2026, 7, 10), 2), report)

    assert [key for key, _ in report.errors] == ["avail-900-2026-07-01"]
    assert "boom" in report.errors[0][1]
    assert report.created == 1
    assert BookingHold.objects.filter(legacy_id="avail-900-2026-07-10").exists()


@pytest.mark.django_db
def test_loaded_block_blocks_the_availability_engine(seeded: Property) -> None:
    from reservations.services.availability import AvailabilityService

    loader = AvailabilityBlockLoader()
    loader._load_rows(_days(date(2026, 7, 25), 3), LoadReport(loader=loader.name))

    assert not AvailabilityService.is_available(seeded, date(2026, 7, 25), date(2026, 7, 28))
    # The half-open end day is a valid new arrival — still available.
    assert AvailabilityService.is_available(seeded, date(2026, 7, 28), date(2026, 7, 30))


@pytest.mark.django_db
def test_run_on_unloaded_property_is_skipped(seeded: Property) -> None:
    loader = AvailabilityBlockLoader()
    report = LoadReport(loader=loader.name)

    loader._load_rows(_days(date(2026, 7, 25), 3, PropertyId=999), report)

    assert BookingHold.objects.count() == 0
    assert report.skipped == 1
    assert report.errors == []


@pytest.mark.django_db
def test_rerun_converges_and_spares_staff_holds(seeded: Property) -> None:
    """Purge-then-insert full replace: a second run converges to the same
    slice (same legacy_ids, same count), and only touches `avail-*` rows —
    staff-created holds (legacy_id NULL) survive."""
    staff_hold = BookingHold.objects.create(
        property=seeded,
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 8),
        reason=BookingHoldReason.MAINTENANCE,
    )
    rows = _days(date(2026, 7, 1), 2) + _days(date(2026, 7, 10), 2)
    loader = AvailabilityBlockLoader()
    loader._load_rows(rows, LoadReport(loader=loader.name))
    first_ids = set(
        BookingHold.objects.filter(legacy_id__startswith=AVAILABILITY_LEGACY_PREFIX).values_list(
            "legacy_id", flat=True
        )
    )

    second = LoadReport(loader=loader.name)
    loader._load_rows(rows, second)

    second_ids = set(
        BookingHold.objects.filter(legacy_id__startswith=AVAILABILITY_LEGACY_PREFIX).values_list(
            "legacy_id", flat=True
        )
    )
    assert first_ids == second_ids == {"avail-900-2026-07-01", "avail-900-2026-07-10"}
    assert second.created == 2 and second.skipped == 0
    assert BookingHold.objects.filter(pk=staff_hold.pk).exists()


@pytest.mark.django_db
def test_run_overlapping_imported_booking_is_skipped(booking: Booking) -> None:
    """A run whose range an imported booking already occupies is skipped, not
    errored — the calendar is blocked either way, and a duplicate block would
    double-paint the grid. (The `booking` fixture occupies 2026-06-10..17.)"""
    loader = AvailabilityBlockLoader()
    report = LoadReport(loader=loader.name)

    loader._load_rows(_days(date(2026, 6, 12), 3), report)

    assert not BookingHold.objects.filter(legacy_id__startswith=AVAILABILITY_LEGACY_PREFIX).exists()
    assert report.skipped == 1
    assert report.errors == []


def test_legacy_query_stamps_load_time_today() -> None:
    query = AvailabilityBlockLoader().legacy_query

    assert f"AvailableDate >= '{timezone.localdate().isoformat()}'" in query
    assert "{today}" not in query


def test_legacy_query_fetches_every_status_with_recency_columns() -> None:
    # The status filter moves after the per-day dedupe, so a newer
    # non-blocking row can supersede an older block.
    query = AvailabilityBlockLoader().legacy_query

    assert "AvailableStatus IN" not in query
    for column in ("Id", "CreatedAt", "UpdatedAt"):
        assert column in query.split("FROM")[0]


# --- reconcile check ---


@pytest.mark.django_db
def test_reconcile_check_counts_days_over_the_avail_slice(seeded: Property) -> None:
    """The loaded side re-expands each `avail-*` block into DAYS with the
    half-open arithmetic `(date_to - date_from).days` — no +1 — and ignores
    staff-created holds."""
    from data_migration.management.commands.reconcile_legacy import _CHECKS

    check = next(c for c in _CHECKS if c.label == "VillaAvailability (future days)")
    assert check.model is BookingHold
    assert "VillaAvailability" in check.legacy_query
    # Mirrors coalesce_runs: latest edit per (property, day) first, then the
    # blocking statuses (BUG-029) — a raw count would include superseded rows.
    assert (
        "ROW_NUMBER() OVER (PARTITION BY PropertyId, CAST(AvailableDate AS date) "
        "ORDER BY COALESCE(UpdatedAt, CreatedAt) DESC, Id DESC)"
    ) in check.legacy_query
    assert "WHERE rn = 1 AND AvailableStatus IN (30, 40, 50, 60)" in check.legacy_query
    assert check.expected_gap == 0

    # Property 133's real run: 2026-07-25..2026-08-22 inclusive = 29 days.
    BookingHold.objects.create(
        property=seeded,
        date_from=date(2026, 7, 25),
        date_to=date(2026, 8, 23),
        reason=BookingHoldReason.MANUAL,
        legacy_id="avail-133-2026-07-25",
    )
    BookingHold.objects.create(  # single grid day -> date_to = day + 1
        property=seeded,
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 2),
        reason=BookingHoldReason.MANUAL,
        legacy_id="avail-900-2026-09-01",
    )
    BookingHold.objects.create(  # staff-created — not in the slice
        property=seeded,
        date_from=date(2026, 10, 1),
        date_to=date(2026, 10, 8),
        reason=BookingHoldReason.MAINTENANCE,
    )

    assert check.loaded_count is not None
    assert check.loaded_count(check.model) == 30
