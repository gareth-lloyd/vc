"""Owner-facing money extraction from a Booking pricing snapshot.

Single source of truth shared by the owner dashboard KPI and the owner
booking serializer. Mirrors `BookingDetailSerializer.get_net_to_owner`:
prefer the explicit `net_to_owner` the engine writes; fall back to
`total - commission - tax` for legacy/older snapshots; return None when the
snapshot lacks the figures (e.g. `{}` on imported rows).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, TypedDict


class OwnerMoney(TypedDict):
    gross_total: Decimal
    commission: Decimal
    tax: Decimal
    net_to_owner: Decimal


def owner_money_from_snapshot(snapshot: dict[str, Any] | None) -> OwnerMoney | None:
    snapshot = snapshot or {}
    try:
        total = Decimal(str(snapshot["total"]))
        commission = Decimal(str(snapshot["commission"]))
        tax = Decimal(str(snapshot["tax"]))
    except (KeyError, InvalidOperation, TypeError):
        return None
    raw_net = snapshot.get("net_to_owner")
    net = total - commission - tax
    if raw_net is not None:
        try:
            net = Decimal(str(raw_net))
        except (InvalidOperation, TypeError):
            pass
    return {"gross_total": total, "commission": commission, "tax": tax, "net_to_owner": net}
