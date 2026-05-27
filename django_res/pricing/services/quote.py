from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass
class QuoteLine:
    """A single-night rate line in a quote breakdown."""

    date: date
    rule_id: int
    card_id: int
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
    breakdown: dict[str, Any] = field(default_factory=dict)
