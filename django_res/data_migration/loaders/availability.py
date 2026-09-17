"""Availability: VillaAvailability -> BookingHold (future non-available runs).

Legacy stored availability as a per-property-day grid (`VillaAvailability`:
PropertyId, AvailableDate, AvailableStatus). The new system replaces the
mechanism entirely — availability is *derived* from range queries over
`Booking.objects.occupying` + `BookingHold.live_overlapping` — so the grid
itself is not ported. Past rows are meaningless (history is carried by the
imported bookings), but FUTURE non-available days are real calendar state
that exists nowhere else in the dump and would otherwise be silently lost.

Strategy:
- SELECT every row with `AvailableDate >= today`, where *today* is
  `timezone.localdate()` stamped into the query at load time — the loaded
  count is therefore dump- and day-relative, not a fixed number.
- De-duplicate to the latest edit per (property, day), THEN keep only the
  blocking statuses (0 Unknown incl. NULL / 6 BookedExt / 30 Unavailable /
  40 On Hold / 50 Booked / 60 Booked VC) — so a newer "Available" row
  supersedes an older block.
- Coalesce consecutive days per property into runs, splitting when the status
  changes, and write one `BookingHold` per run (split around existing
  occupancy, below): source-less, `reason=MANUAL`
  (permitted by `bookinghold_has_source_or_blocking_reason`, and the
  operator-editable reason so staff can manage imported blocks on the admin
  grid), never-expiring (`expires_at=NULL`), with the legacy status name /
  CreatedBy / day notes preserved in `notes`. No `BookingHoldReason` value
  maps onto the legacy statuses semantically (a legacy "Booked" day has no
  Booking row to hang a booking-hold off), so MANUAL is deliberate.
- The model's date range is half-open `[date_from, date_to)` (see
  `BookingHold.live_overlapping`), so a run of inclusive grid days
  `start..end` lands as `date_from=start, date_to=end + 1 day`.
- Idempotency is full-replace of this loader's own slice: runs have no stable
  legacy pk (the grid's day rows do, the coalesced run doesn't), so upsert
  keying is impossible — purge every `avail-*` hold, then insert (mirrors
  `RateBandLoader`). The deterministic `legacy_id` is
  `avail-{PropertyId}-{run start ISO date}`.
- A run is written around what already occupies the calendar (BUG-030 §31):
  the ranges of imported bookings (`Booking.objects.occupying`) and every
  unreleased non-legacy hold are subtracted and each
  remaining sub-range becomes its own hold, keyed by its own start day. A
  run fully covered is SKIPPED with a warning, not errored. The days trimmed
  are logged per run and in total (`trimmed_days`), so the reconcile gap is
  auditable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, ClassVar

import structlog
from django.db import transaction
from django.utils import timezone

from data_migration.base import BaseLoader, LoadReport
from properties.models.property import Property
from reservations.enums import BookingHoldReason, BookingHoldStatus
from reservations.models.booking import Booking, BookingHold

logger = structlog.get_logger(__name__)

# The `legacy_id` namespace of this loader's slice — the purge and the
# reconcile check both key on it.
AVAILABILITY_LEGACY_PREFIX = "avail-"

# Legacy `AvailabilityStatus.Code` -> display name. The loader imports only
# the non-available subset; the full map is kept so a note can always name
# whatever status a row carried.
STATUS_NAMES = {
    0: "Unknown",
    6: "BookedExt",  # AvailabilityStatus row Id 7 carries Code 6
    10: "Available",
    20: "Avail-Enquire",
    30: "Unavailable",
    40: "On Hold",
    50: "Booked",
    60: "Booked VC",
    70: "Available",
}

# The statuses that block the calendar — the only ones imported. BUG-030 §31:
# 0 "Unknown" (NULL coalesces to it) is how staff entered whole-calendar
# blocks, and legacy's rate lookup books only a literal "Available" day, so it
# blocked there; 6 "BookedExt" is an external booking, on a par with 50/60.
# 20 "Available - Enquire" stays bookable (not decided otherwise).
BLOCKING_STATUSES = frozenset({0, 6, 30, 40, 50, 60})


@dataclass
class _Run:
    """One coalesced per-property run of consecutive same-status days.

    `start`/`end` are both *inclusive* grid days — the half-open shift to the
    model's `[date_from, date_to)` happens at write time.
    """

    property_id: int
    status: int
    start: date
    end: date
    created_by: str
    notes: list[str] = field(default_factory=list)


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    if hasattr(value, "date"):  # datetime -> date
        return value.date()
    return value


def _recency(row: dict[str, Any]) -> tuple[datetime, int]:
    """Latest-edit key for duplicate grid rows. Legacy updates rows in place
    and stamps `UpdatedAt` (inserts leave it NULL), so `Id` alone is not
    recency; it only breaks ties."""
    stamp = row.get("UpdatedAt") or row.get("CreatedAt") or datetime.min
    return (stamp, int(row.get("Id") or 0))


def coalesce_runs(rows: list[dict[str, Any]]) -> list[_Run]:
    """Coalesce per-day grid rows into runs of consecutive same-status days.

    Pure function of the row set: rows are sorted here (not trusted from the
    query) and de-duplicated per (property, day) to the latest edit
    (`_recency`) — the grid should be unique per day, but the dump holds 380
    duplicate pairs, 208 with differing statuses (BUG-029). Non-blocking
    statuses are dropped only after that dedupe. A run breaks on: property
    change, a calendar gap, or a status change. Day-level `Notes` are collected (distinct,
    date order) onto the run; `CreatedBy` is the run's first day's value.

    Legacy `Notes` is almost always the day's status code echoed back as a
    string (14k "50" rows, 878 "70", ... vs 30 genuinely informative
    "confirmed" rows on the reference dump) — a note equal to the day's own
    status code carries no information and is dropped.
    """
    keyed: dict[tuple[int, date], dict[str, Any]] = {}
    for row in rows:
        day = _as_date(row.get("AvailableDate"))
        if day is None or row.get("PropertyId") is None:
            continue
        key = (int(row["PropertyId"]), day)
        if key not in keyed or _recency(row) > _recency(keyed[key]):
            keyed[key] = row

    runs: list[_Run] = []
    current: _Run | None = None
    for (property_id, day), row in sorted(keyed.items()):
        status = int(row.get("AvailableStatus") or 0)
        if status not in BLOCKING_STATUSES:
            continue
        if (
            current is None
            or property_id != current.property_id
            or status != current.status
            or day != current.end + timedelta(days=1)
        ):
            current = _Run(
                property_id=property_id,
                status=status,
                start=day,
                end=day,
                created_by=str(row.get("CreatedBy") or "").strip(),
            )
            runs.append(current)
        else:
            current.end = day
        note = str(row.get("Notes") or "").strip()
        if note and note != str(status) and note not in current.notes:
            current.notes.append(note)
    return runs


def free_ranges(
    date_from: date, date_to: date, occupied: list[tuple[date, date]]
) -> list[tuple[date, date]]:
    """The half-open sub-ranges of `[date_from, date_to)` not covered by any
    of the half-open `occupied` ranges (in any order, may overlap)."""
    free: list[tuple[date, date]] = []
    cursor = date_from
    for start, end in sorted(occupied):
        if end <= cursor:
            continue
        if start >= date_to:
            break
        if start > cursor:
            free.append((cursor, start))
        cursor = max(cursor, end)
        if cursor >= date_to:
            return free
    if cursor < date_to:
        free.append((cursor, date_to))
    return free


def _run_notes(run: _Run) -> str:
    status_name = STATUS_NAMES.get(run.status, f"code {run.status}")
    provenance = f"Imported from legacy availability (status {status_name}"
    if run.created_by:
        provenance += f", created by {run.created_by}"
    provenance += ")"
    if run.notes:
        return provenance + "\n" + "\n".join(run.notes)
    return provenance


def _run_legacy_id(run: _Run) -> str:
    return f"{AVAILABILITY_LEGACY_PREFIX}{run.property_id}-{run.start.isoformat()}"


class AvailabilityBlockLoader(BaseLoader):
    """VillaAvailability (future non-available days) -> BookingHold runs.

    See the module docstring for the strategy. Each pass is a full replace of
    the `avail-*` slice; staff-created holds (`legacy_id` NULL) and every
    other loader's rows are untouched.
    """

    name = "availability_block"
    target_model = BookingHold
    legacy_pk_column: ClassVar[str] = "PropertyId"

    @property
    def legacy_query(self) -> str:  # type: ignore[override]
        # Load-time "today": the load window (and so the loaded block count)
        # is relative to the day the loader runs.
        return (
            "SELECT Id, PropertyId, AvailableDate, AvailableStatus, Notes, CreatedBy, "
            "CreatedAt, UpdatedAt "
            "FROM VillaAvailability "
            f"WHERE AvailableDate >= '{timezone.localdate().isoformat()}' "
            "ORDER BY PropertyId, AvailableDate, Id"
        )

    def transform(self, row: dict[str, Any]) -> dict[str, Any] | None:  # pragma: no cover
        raise NotImplementedError("AvailabilityBlockLoader writes runs via _load_rows")

    def _load_rows(self, rows: list[dict[str, Any]], report: LoadReport) -> None:
        runs = coalesce_runs(rows)
        created = 0
        self._trimmed_days = 0
        with transaction.atomic():
            purged, _ = BookingHold.objects.filter(
                legacy_id__startswith=AVAILABILITY_LEGACY_PREFIX
            ).delete()
            property_cache: dict[str, Property | None] = {}
            for run in runs:
                # Per-run savepoint (BUG-029 §4): a write-time failure is
                # recorded against the run and the remaining runs still load.
                try:
                    with transaction.atomic():
                        created += self._load_run(run, property_cache, report)
                except Exception as exc:  # isolate one bad run from the rest
                    report.errors.append((_run_legacy_id(run), repr(exc)))
        report.created += created
        logger.info(
            "data_migration.availability_block_loaded",
            purged=purged,
            day_rows=len(rows),
            runs=len(runs),
            created=created,
            skipped=report.skipped,
            trimmed_days=self._trimmed_days,
        )

    _trimmed_days = 0

    def _load_run(
        self, run: _Run, property_cache: dict[str, Property | None], report: LoadReport
    ) -> int:
        """Write one run as holds around existing occupancy; the hold count
        (0 when the run is skipped)."""
        key = str(run.property_id)
        if key not in property_cache:
            property_cache[key] = Property.objects.filter(legacy_id=key).first()
        prop = property_cache[key]
        date_from = run.start
        date_to = run.end + timedelta(days=1)  # inclusive run -> half-open hold
        if prop is None:
            report.skipped += 1
            logger.warning(
                "data_migration.availability_block_property_missing",
                property_legacy_id=key,
                date_from=date_from.isoformat(),
                date_to=date_to.isoformat(),
            )
            return 0
        # Write around what already blocks the calendar: a duplicate block
        # would double-paint the grid, but skipping the whole run (the old
        # rule) left a whole-calendar block bookable around one booking.
        # Post-purge, any surviving hold here is staff-created or another
        # source's — never our own slice.
        occupied = [
            (b.date_from, b.date_to)
            for b in Booking.objects.occupying(property=prop, date_from=date_from, date_to=date_to)
        ] + [
            # Every LIVE hold, not just `live_overlapping`: the
            # `bookinghold_no_overlap_live` exclusion constraint also covers
            # a lapsed-but-unswept LIVE hold, which would fail the insert.
            (h.date_from, h.date_to)
            for h in BookingHold.objects.filter(
                property=prop,
                status=BookingHoldStatus.LIVE.value,
                date_from__lt=date_to,
                date_to__gt=date_from,
            )
        ]
        pieces = free_ranges(date_from, date_to, occupied)
        trimmed = (date_to - date_from).days - sum((end - start).days for start, end in pieces)
        if trimmed:
            logger.warning(
                "data_migration.availability_block_range_occupied",
                property_id=prop.pk,
                property_legacy_id=key,
                date_from=date_from.isoformat(),
                date_to=date_to.isoformat(),
                trimmed_days=trimmed,
                pieces=len(pieces),
            )
        if not pieces:
            report.skipped += 1
            self._trimmed_days += trimmed
            return 0
        for start, end in pieces:
            BookingHold.objects.create(
                property=prop,
                date_from=start,
                date_to=end,
                expires_at=None,  # never expires — released only by staff
                reason=BookingHoldReason.MANUAL,
                notes=_run_notes(run),
                legacy_id=f"{AVAILABILITY_LEGACY_PREFIX}{run.property_id}-{start.isoformat()}",
            )
        # Counted only once the run's holds are written: an errored run rolls
        # back to its savepoint and must not claim trimmed days.
        self._trimmed_days += trimmed
        return len(pieces)
