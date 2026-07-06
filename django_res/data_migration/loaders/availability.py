"""Availability: VillaAvailability -> BookingHold (future non-available runs).

Legacy stored availability as a per-property-day grid (`VillaAvailability`:
PropertyId, AvailableDate, AvailableStatus). The new system replaces the
mechanism entirely — availability is *derived* from range queries over
`Booking.objects.occupying` + `BookingHold.live_overlapping` — so the grid
itself is not ported. Past rows are meaningless (history is carried by the
imported bookings), but FUTURE non-available days are real calendar state
that exists nowhere else in the dump and would otherwise be silently lost.

Strategy:
- SELECT the non-available statuses (30 Unavailable / 40 On Hold / 50 Booked /
  60 Booked VC) with `AvailableDate >= today`, where *today* is
  `timezone.localdate()` stamped into the query at load time — the loaded
  count is therefore dump- and day-relative, not a fixed number.
- Coalesce consecutive days per property into runs, splitting when the status
  changes, and write ONE `BookingHold` per run: source-less, `reason=MANUAL`
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
- A run whose range is already occupied by an imported booking (or a live
  non-legacy hold) is SKIPPED with a warning, not errored: the calendar is
  already blocked, and a duplicate block would double-paint the grid.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, ClassVar

import structlog
from django.db import transaction
from django.utils import timezone

from data_migration.base import BaseLoader, LoadReport
from properties.models.property import Property
from reservations.enums import BookingHoldReason
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
    10: "Available",
    20: "Avail-Enquire",
    30: "Unavailable",
    40: "On Hold",
    50: "Booked",
    60: "Booked VC",
    70: "Available",
}


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


def coalesce_runs(rows: list[dict[str, Any]]) -> list[_Run]:
    """Coalesce per-day grid rows into runs of consecutive same-status days.

    Pure function of the row set: rows are sorted here (not trusted from the
    query) and de-duplicated per (property, day) keep-first — the grid should
    be unique per day, but a dirty duplicate must merge, not mint a second run
    with a colliding `legacy_id`. A run breaks on: property change, a calendar
    gap, or a status change. Day-level `Notes` are collected (distinct,
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
        keyed.setdefault((int(row["PropertyId"]), day), row)

    runs: list[_Run] = []
    current: _Run | None = None
    for (property_id, day), row in sorted(keyed.items()):
        status = int(row.get("AvailableStatus") or 0)
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


def _run_notes(run: _Run) -> str:
    status_name = STATUS_NAMES.get(run.status, f"code {run.status}")
    provenance = f"Imported from legacy availability (status {status_name}"
    if run.created_by:
        provenance += f", created by {run.created_by}"
    provenance += ")"
    if run.notes:
        return provenance + "\n" + "\n".join(run.notes)
    return provenance


class AvailabilityBlockLoader(BaseLoader):
    """VillaAvailability (future non-available days) -> BookingHold runs.

    See the module docstring for the strategy. Each pass is a full replace of
    the `avail-*` slice; staff-created holds (`legacy_id` NULL) and every
    other loader's rows are untouched.
    """

    name = "availability_block"
    target_model = BookingHold
    legacy_pk_column: ClassVar[str] = "PropertyId"
    # `{today}` is stamped by `_apply_since` at query time — the load window
    # (and so the loaded block count) is relative to the day the loader runs.
    legacy_query = (
        "SELECT PropertyId, AvailableDate, AvailableStatus, Notes, CreatedBy "
        "FROM VillaAvailability "
        "WHERE AvailableStatus IN (30, 40, 50, 60) "
        "AND AvailableDate >= '{today}' "
        "ORDER BY PropertyId, AvailableDate"
    )

    def _apply_since(self, query: str) -> str:
        # Deliberate `--since` no-op (mirrors rate_rule): run coalescing is a
        # function of the whole future window, so a delta slice would split
        # runs at the delta boundary and orphan last run's blocks. Every pass
        # is a full replace of the loader's own slice. This override is also
        # the query-build seam: it stamps load-time "today" into the template.
        if self.since:
            logger.warning(
                "data_migration.availability_block_since_ignored",
                since=str(self.since),
                reason="run coalescing needs the full future window; full reload",
            )
        return query.format(today=timezone.localdate().isoformat())

    def transform(self, row: dict[str, Any]) -> dict[str, Any] | None:  # pragma: no cover
        raise NotImplementedError("AvailabilityBlockLoader writes runs via _load_rows")

    def _load_rows(self, rows: list[dict[str, Any]], report: LoadReport) -> None:
        runs = coalesce_runs(rows)
        created = 0
        with transaction.atomic():
            purged, _ = BookingHold.objects.filter(
                legacy_id__startswith=AVAILABILITY_LEGACY_PREFIX
            ).delete()
            property_cache: dict[str, Property | None] = {}
            for run in runs:
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
                    continue
                # Skip-not-error when the range is already occupied: the
                # calendar is blocked either way, and a duplicate block would
                # double-paint the grid. Post-purge, any surviving hold here
                # is staff-created or another source's — never our own slice.
                occupied_by_booking = Booking.objects.occupying(
                    property=prop, date_from=date_from, date_to=date_to
                ).exists()
                if (
                    occupied_by_booking
                    or BookingHold.live_overlapping(
                        property=prop, date_from=date_from, date_to=date_to
                    ).exists()
                ):
                    report.skipped += 1
                    logger.warning(
                        "data_migration.availability_block_range_occupied",
                        property_id=prop.pk,
                        property_legacy_id=key,
                        date_from=date_from.isoformat(),
                        date_to=date_to.isoformat(),
                        by="booking" if occupied_by_booking else "hold",
                    )
                    continue
                BookingHold.objects.create(
                    property=prop,
                    date_from=date_from,
                    date_to=date_to,
                    expires_at=None,  # never expires — released only by staff
                    reason=BookingHoldReason.MANUAL,
                    notes=_run_notes(run),
                    legacy_id=f"{AVAILABILITY_LEGACY_PREFIX}{run.property_id}-{run.start.isoformat()}",
                )
                created += 1
        report.created += created
        logger.info(
            "data_migration.availability_block_loaded",
            purged=purged,
            day_rows=len(rows),
            runs=len(runs),
            created=created,
            skipped=report.skipped,
        )
