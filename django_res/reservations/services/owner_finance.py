"""Owner-facing money extraction from a Booking pricing snapshot.

Single source of truth shared by the owner dashboard KPI and the owner
booking serializer. Mirrors `BookingDetailSerializer.get_net_to_owner`:
prefer the explicit `net_to_owner` the engine writes; fall back to
`total - commission - tax` for legacy/older snapshots; return None when the
snapshot lacks the figures (e.g. `{}` on imported rows).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any, TypedDict

from reservations.services.charges import (
    charges_total_for,
    effective_commission_for,
    owner_effect,
)

if TYPE_CHECKING:
    from reservations.models import Booking


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


def owner_money_for_booking(booking: Booking) -> OwnerMoney | None:
    """Snapshot money plus the manual-charge owner effect.

    Charges live outside the immutable snapshot and enter the
    commissionable base (legacy-style — see `services.charges`), so the
    owner surfaces must layer them on exactly like the staff
    `BookingDetailSerializer.get_net_to_owner` does, or the two APIs
    report different money for the same booking.
    """
    money = owner_money_from_snapshot(booking.pricing_snapshot)
    if money is None:
        return None
    charges_total = charges_total_for(booking)
    if not charges_total:
        return money
    commission_cfg = effective_commission_for(booking) or {}
    effect = owner_effect(
        charges_total,
        commission_cfg.get("calculation_type"),
        commission_cfg.get("amount"),
    )
    return {
        "gross_total": money["gross_total"] + charges_total,
        "commission": money["commission"] + effect.commission_on_charges,
        "tax": money["tax"],
        "net_to_owner": money["net_to_owner"] + effect.owner_delta,
    }
