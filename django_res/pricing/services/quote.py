from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass
class QuoteLine:
    """A single-night rate line in a quote breakdown.

    `band_id` / `period_id` are `None` for a synthetic fallback line — a night
    priced from `RatePlan.fallback_nightly` because no `RateBand` covered it
    (see GAP-008 / the legacy `SettingNightlyPrice` path). GAP-056: the date-axis
    parent is the `RatePeriod` now (was the dropped `RateCard`).
    """

    date: date
    band_id: int | None
    period_id: int | None
    nightly: Decimal
    notes: str = ""
    # Q-018: the base nightly when a reduction changed this night's price;
    # None for an unreduced (or fallback) night.
    reduced_from: Decimal | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date.isoformat(),
            "band_id": self.band_id,
            "period_id": self.period_id,
            "nightly": str(self.nightly),
            "notes": self.notes,
            "reduced_from": str(self.reduced_from) if self.reduced_from is not None else None,
        }


@dataclass
class AppliedExtra:
    """An Extra row that was applied at quote time, plus its computed amount.

    `commissionable=False` (GAP-076) means the amount bills the guest but is
    excluded from the commission/tax bases and passes through to the owner.
    """

    extra_id: int
    name: str
    kind: str
    calc: str
    computed_amount: Decimal
    commissionable: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "extra_id": self.extra_id,
            "name": self.name,
            "kind": self.kind,
            "calc": self.calc,
            "computed_amount": str(self.computed_amount),
            "commissionable": self.commissionable,
        }


@dataclass
class Quote:
    """Result of `PricingEngine.quote()`. The `breakdown` is JSON-snapshotable."""

    property_id: int
    currency_code: str
    party: int
    date_from: date
    date_to: date
    lines: list[QuoteLine]
    rate_subtotal: Decimal
    extras: list[AppliedExtra]
    extras_total: Decimal
    # GAP-076: the base commission/tax were derived from (basis-dependent — the
    # gross under GROSS, the owner net under NET) and the pass-through slice of
    # `extras_total` that was excluded from it.
    commission_base: Decimal
    extras_non_commissionable_total: Decimal
    discount: Decimal
    commission: Decimal
    tax: Decimal
    total: Decimal
    net_to_owner: Decimal
    # Q-018: what the stay would have cost without any rate reduction — both
    # None when no priced band carried one. `total_before_reduction` re-runs
    # the basis math on the un-reduced base (under NET the gross-up scales
    # with the base, so it is NOT total + subtotal delta).
    rate_subtotal_before_reduction: Decimal | None = None
    total_before_reduction: Decimal | None = None
    changeover_shifted_from: date | None = None
    # True when no real plan covered the stay and the quote was derived from a
    # prior year's rates — a guide rate, not a confirmed price. The provenance
    # lives in `breakdown["projection"]`.
    is_projected: bool = False
    breakdown: dict[str, Any] = field(default_factory=dict)
