from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass
class QuoteLine:
    """A single-night rate line in a quote breakdown.

    `rule_id` / `card_id` are `None` for a synthetic fallback line — a night
    priced from `RatePlan.fallback_nightly` because no `RateRule` covered it
    (see GAP-008 / the legacy `SettingNightlyPrice` path).
    """

    date: date
    rule_id: int | None
    card_id: int | None
    nightly: Decimal
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date.isoformat(),
            "rule_id": self.rule_id,
            "card_id": self.card_id,
            "nightly": str(self.nightly),
            "notes": self.notes,
        }


@dataclass
class AppliedExtra:
    """An Extra row that was applied at quote time, plus its computed amount."""

    extra_id: int
    name: str
    kind: str
    calc: str
    computed_amount: Decimal

    def to_dict(self) -> dict[str, Any]:
        return {
            "extra_id": self.extra_id,
            "name": self.name,
            "kind": self.kind,
            "calc": self.calc,
            "computed_amount": str(self.computed_amount),
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
    discount: Decimal
    commission: Decimal
    tax: Decimal
    total: Decimal
    net_to_owner: Decimal
    changeover_shifted_from: date | None = None
    # True when no real plan covered the stay and the quote was derived from a
    # prior year's rates — a guide rate, not a confirmed price. The provenance
    # lives in `breakdown["projection"]`.
    is_projected: bool = False
    breakdown: dict[str, Any] = field(default_factory=dict)
