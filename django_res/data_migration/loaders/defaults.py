"""PropertyDefaults loader — legacy `VillaConfigPropertyDefault` (GAP-070).

The legacy table is effectively a singleton (`SP_CRUD_VillaConfigPropertyDefault`
upserts one row) and maps onto the `PropertyDefaults` singleton (`pk=1`), so
this loader deviates from the `legacy_id`-keyed upsert convention: it applies
the first legacy row onto `PropertyDefaults.get_solo()` and never writes a
`legacy_id` (the model has none). Idempotent — re-running re-applies the same
values.

`--since` SKIPS the loader entirely (with a warning): during the cutover
window staff may correct the defaults through the new
`PATCH /property-defaults` endpoint, and a delta run must not clobber those
edits with the stale legacy row. A full (no `--since`) re-run re-applies
legacy deliberately.

Deliberately NOT mapped (matching `PropertyLoader._write_settings`, which
ignores the same legacy columns on VillaMaster):
- `AvailabilityStatus` / `PricesEnteredType` — the port hardcodes
  AVAILABLE / GROSS everywhere legacy carried these ids.
- `SecurityDepositCalculateFrom` — no schema equivalent.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import structlog

from data_migration.base import BaseLoader, LoadReport
from data_migration.loaders.finance import (
    _COMMISSION_TYPE_MAP,
    _DEPOSIT_TYPE_MAP,
    _SEC_DEPOSIT_TYPE_MAP,
    _decimal,
)
from data_migration.loaders.properties import _DAY_MAP
from pricing.models.currency import Currency
from properties.models.defaults import PropertyDefaults

logger = structlog.get_logger(__name__)


def _defaults_updates(row: dict[str, Any]) -> dict[str, Any]:
    """Translate the legacy row into PropertyDefaults field updates.

    Every PropertyDefaults column is non-nullable with a seeded default, so a
    NULL (or junk/unmappable) legacy value is *omitted* — the current
    singleton value stays — rather than written through as None.
    """
    updates: dict[str, Any] = {}

    def put(field: str, value: Any) -> None:
        if value is None:
            return
        # Negative numerics are legacy junk (same guard as `_finance_defaults`).
        if not isinstance(value, bool) and isinstance(value, (int, Decimal)) and value < 0:
            return
        updates[field] = value

    if row.get("IsBookingsRequirePreApproval") is not None:
        put("bookings_require_pre_approval", bool(row["IsBookingsRequirePreApproval"]))
    put("check_in_time", row.get("CheckinTime"))
    put("check_out_time", row.get("CheckOutTime"))
    # `_DAY_MAP` keys are `ChangeOverDays.Code`: -1 = Open/flexible (→ ANY)
    # and 0 = Sunday are real values, so no `or 0` — only NULL means unset.
    day_code = row.get("ChangeOverDay")
    put("changeover_day", _DAY_MAP.get(day_code) if day_code is not None else None)
    nights = _decimal(row.get("MinimumNightsRental"))
    put("min_nights_rental", int(nights) if nights is not None else None)

    put("commission_calculation_type", _COMMISSION_TYPE_MAP.get(row.get("CommissionType") or 0))
    put("commission_amount", _decimal(row.get("CommissionAmount")))

    if row.get("IsDepositRequired") is not None:
        put("deposit_required", bool(row["IsDepositRequired"]))
    put("deposit_calculation_type", _DEPOSIT_TYPE_MAP.get(row.get("DepositType") or 0))
    put("deposit_amount", _decimal(row.get("DepositAmount")))
    if row.get("IsInterimRequired") is not None:
        put("interim_required", bool(row["IsInterimRequired"]))
    put("interim_calculation_type", _DEPOSIT_TYPE_MAP.get(row.get("InterimType") or 0))
    put("interim_amount", _decimal(row.get("InterimAmount")))
    put("days_interim_due_before_arrival", row.get("DaysInterimDueBeforeArrival"))
    put("days_balance_due_before_arrival", row.get("DaysBalanceDueBeforeArrival"))

    if row.get("SecurityDepositRequired") is not None:
        put("security_deposit_required", bool(row["SecurityDepositRequired"]))
    put(
        "security_deposit_calculation_type",
        _SEC_DEPOSIT_TYPE_MAP.get(row.get("SecurityDepositAmountType") or 0),
    )
    put("security_deposit_amount", _decimal(row.get("SecurityDepositAmount")))
    put(
        "security_deposit_days_due_before_arrival",
        row.get("SecurityDepositDaysDueBeforeArrival"),
    )
    # The legacy DB column really is the `Defunded` typo (see
    # design/departures.md) — map it onto the clean field name.
    put(
        "security_deposit_days_refunded_after_departure",
        row.get("SecurityDepositDaysDefundedAfterDeparture"),
    )
    return updates


class PropertyDefaultsLoader(BaseLoader):
    """VillaConfigPropertyDefault (singleton) -> PropertyDefaults (pk=1)."""

    name = "property_defaults"
    target_model = PropertyDefaults
    legacy_query = (
        "SELECT Id, IsBookingsRequirePreApproval, CurrencyId, "
        "CommissionType, CommissionAmount, CheckinTime, CheckOutTime, "
        "ChangeOverDay, MinimumNightsRental, "
        "IsDepositRequired, DepositType, DepositAmount, "
        "IsInterimRequired, InterimType, InterimAmount, "
        "DaysInterimDueBeforeArrival, DaysBalanceDueBeforeArrival, "
        "SecurityDepositRequired, SecurityDepositAmountType, "
        "SecurityDepositAmount, SecurityDepositDaysDueBeforeArrival, "
        "SecurityDepositDaysDefundedAfterDeparture "
        "FROM VillaConfigPropertyDefault ORDER BY Id"
    )

    def _apply_since(self, query: str) -> str:
        # Deliberate no-op: the table has no `UpdatedAt` (its audit column is
        # `Updatedon`), and the skip decision lives in `_load_rows`.
        return query

    def _load_rows(self, rows: list[dict[str, Any]], report: LoadReport) -> None:
        if self.since:
            # Delta runs must not clobber operator edits made through the new
            # PATCH /property-defaults endpoint during the cutover window.
            logger.warning(
                "data_migration.property_defaults_since_skipped",
                since=str(self.since),
                reason="singleton re-apply would clobber cutover-window operator edits",
            )
            report.skipped += 1
            return
        if not rows:
            report.skipped += 1
            return
        # Effectively a singleton; first row wins (same convention as
        # `_fetch_contact_default_finance` for duplicate legacy rows).
        try:
            self._apply(rows[0], report)
        except Exception as exc:  # match BaseLoader's per-row error isolation
            report.errors.append((str(rows[0].get("Id")), repr(exc)))

    def _apply(self, row: dict[str, Any], report: LoadReport) -> None:
        updates = _defaults_updates(row)
        if row.get("CurrencyId"):
            currency = Currency.objects.filter(legacy_id=str(row["CurrencyId"])).first()
            if currency is not None:
                updates["currency"] = currency
        defaults = PropertyDefaults.get_solo()
        for field, value in updates.items():
            setattr(defaults, field, value)
        defaults.save()
        report.updated += 1
