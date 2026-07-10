"""Owner-facing money extraction from a Booking pricing snapshot.

Single source of truth shared by the owner dashboard KPI and the owner
booking serializer. Mirrors `BookingDetailSerializer.get_net_to_owner`:
prefer the explicit `net_to_owner` the engine writes; fall back to
`total - commission - tax` for legacy/older snapshots; return None when the
snapshot lacks the figures (e.g. `{}` on imported rows).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any, TypedDict

from reservations.services.charges import charges_owner_adjustments

if TYPE_CHECKING:
    from collections.abc import Sequence

    from reservations.models import Booking

CENT = Decimal("0.01")

# Payments vocabulary as string literals: `reservations` sits below `payments`
# in the import spine and must not import its enums (same pattern as
# `BookingDetailSerializer.get_amount_paid`). Agreement with the real enums —
# and with `TrackSerializer`'s "scheduled" semantics — is pinned by
# `payments/tests/test_component_splits_parity.py`.
_SCHEDULE_PURPOSES = ("deposit", "balance")
_TERMINAL_NON_ACTIVE = frozenset({"cancelled", "expired", "failed"})


class OwnerMoney(TypedDict):
    gross_total: Decimal
    commission: Decimal
    tax: Decimal
    net_to_owner: Decimal


class ComponentSplit(TypedDict):
    purpose: str
    status: str
    due_at: datetime | None
    gross: Decimal
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
    adjust = charges_owner_adjustments(booking)
    if not any(adjust):
        return money
    return {
        "gross_total": money["gross_total"] + adjust.gross_delta,
        "commission": money["commission"] + adjust.commission_delta,
        "tax": money["tax"],
        "net_to_owner": money["net_to_owner"] + adjust.net_delta,
    }


def allocate_proportionally(
    *, commission: Decimal, tax: Decimal, grosses: Sequence[Decimal]
) -> list[tuple[Decimal, Decimal]]:
    """Split whole-booking commission and tax across components pro-rata.

    Every component except the last takes its gross-share slice quantized
    to a cent (half-even); the last takes the exact residual, so Σ
    commission and Σ tax reproduce the inputs — the residual lands on
    BALANCE just like the scheduler's odd cent. Quantization is at the
    snapshot's flat-2dp grain (the engine writes all snapshot money at
    2dp regardless of currency), deliberately NOT the scheduler's
    per-currency `quantise_money` — the inputs being allocated are
    snapshot figures. A zero-gross schedule allocates nothing (no
    division, and the whole commission/tax stays unallocated). With three
    or more components, cumulative over-rounding can make the last slice
    slightly negative — still conservation-correct.
    """
    total_gross = sum(grosses, Decimal("0"))
    if not grosses:
        return []
    if total_gross == 0:
        return [(Decimal("0.00"), Decimal("0.00"))] * len(grosses)
    allocations: list[tuple[Decimal, Decimal]] = []
    commission_left, tax_left = commission, tax
    for gross in grosses[:-1]:
        commission_i = (commission * gross / total_gross).quantize(CENT)
        tax_i = (tax * gross / total_gross).quantize(CENT)
        allocations.append((commission_i, tax_i))
        commission_left -= commission_i
        tax_left -= tax_i
    allocations.append((commission_left, tax_left))
    return allocations


def payment_component_splits(
    booking: Booking, *, money: OwnerMoney | None = None
) -> list[ComponentSplit] | None:
    """GAP-077: per-component (deposit/balance) gross/commission/tax/net.

    Derive-on-read — the whole-booking owner money (snapshot + charge
    overlay) is allocated across the schedule components by gross share, so
    a re-price (which rewrites the snapshot and resyncs the schedule) is
    automatically reflected. Returns None when the booking has no owner
    money (sparse/imported snapshot), `[]` when it has no schedule rows
    (financeless property).

    Per-component gross/status/due_at mirror `TrackSerializer`'s semantics
    (gross = Σ rows with status ∉ {cancelled, expired, failed}; status =
    latest row's, created_at then pk; due_at = earliest scheduled due
    date, including settled rows). The payments walk filters in Python
    over `booking.payments.all()`, so `prefetch_related("payments")`
    covers it — but the charge overlay inside `owner_money_for_booking`
    still costs its own queries unless the queryset carries the
    `with_charges_total` annotations + `select_related("property__finance")`,
    or the caller passes its already-computed `money` in.

    Σ component gross ≠ booking gross is a routine state (partial
    mark-paid, manual track rows, resync residual). Allocation runs over
    the *scheduled* gross, so whenever any gross is scheduled Σ
    commission/tax equal the whole-booking figures and every row satisfies
    `net = gross - commission - tax` (an all-zero schedule allocates
    nothing); Σ net then differs from the whole-booking net by exactly
    the schedule drift — surfaced by the FE as a caveat, not reconciled
    here.
    """
    if money is None:
        money = owner_money_for_booking(booking)
    if money is None:
        return None
    rows = list(booking.payments.all())
    components: list[dict[str, Any]] = []
    for purpose in _SCHEDULE_PURPOSES:
        purpose_rows = [p for p in rows if p.purpose == purpose]
        if not purpose_rows:
            continue
        scheduled = [p for p in purpose_rows if p.status not in _TERMINAL_NON_ACTIVE]
        latest = max(purpose_rows, key=lambda p: (p.created_at, p.pk))
        components.append(
            {
                "purpose": purpose,
                "status": latest.status,
                "due_at": min((p.due_at for p in scheduled if p.due_at is not None), default=None),
                "gross": sum((p.amount for p in scheduled), Decimal("0.00")),
            }
        )
    if not components:
        return []
    allocations = allocate_proportionally(
        commission=money["commission"],
        tax=money["tax"],
        grosses=[c["gross"] for c in components],
    )
    return [
        ComponentSplit(
            purpose=component["purpose"],
            status=component["status"],
            due_at=component["due_at"],
            gross=component["gross"],
            commission=commission_i,
            tax=tax_i,
            net_to_owner=component["gross"] - commission_i - tax_i,
        )
        for component, (commission_i, tax_i) in zip(components, allocations, strict=True)
    ]
