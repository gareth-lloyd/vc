"""Charge-item service — manual charge/credit lines on a booking.

`ChargeItemService` is the only sanctioned write path: it locks the
booking, gates on the active states, pins the currency to the booking's,
refuses a negative combined total, and writes the BookingEvent audit
trail. The `booking_total_changed` → payments resync chain hangs off the
model signals, so it fires for these writes and for direct ORM writes
alike.

Owner-side accounting (`owner_effect`) follows legacy: manual charges
enter the commissionable base. The guest always pays the entered amount
verbatim; the helper only answers how that money splits between owner
and agency.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any, NamedTuple

from django.db import models, transaction
from django.db.models.functions import Coalesce

from core.exceptions import DomainValidationError, InvalidTransition
from properties.enums import CommissionCalcType
from reservations.enums import ACTIVE_BOOKING_STATUSES

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from pricing.models import Currency
    from reservations.models import Booking, BookingChargeItem

ZERO = Decimal("0.00")


def with_charges_total(qs: QuerySet[Booking]) -> QuerySet[Booking]:
    """Annotate Σ charge items as `charges_total` on a Booking queryset.

    A Subquery (not a Sum over a join) on purpose: it lives only in the
    SELECT clause, so it can't cross-multiply with other LEFT-JOIN
    aggregates (e.g. `amount_paid`) or leak into status-counts/paginator
    COUNTs. Coalesce to a real 0 so an annotated NULL never trips the
    per-row fallback in `charges_total_for`.
    """
    from reservations.models import BookingChargeItem

    charge_sum = (
        BookingChargeItem.objects.filter(booking=models.OuterRef("pk"))
        .values("booking")
        .annotate(s=models.Sum("amount"))
        .values("s")
    )
    return qs.annotate(
        charges_total=Coalesce(
            models.Subquery(charge_sum),
            models.Value(Decimal("0")),
            output_field=models.DecimalField(max_digits=12, decimal_places=2),
        )
    )


def charges_total_for(booking: Booking) -> Decimal:
    """Live Σ of the booking's charge items (no denormalised column by design).

    Reads the `with_charges_total` annotation when present (Coalesce
    guarantees a real 0 there, so None means "un-annotated"); falls back
    to a per-row aggregate.
    """
    total = getattr(booking, "charges_total", None)
    if total is None:
        total = booking.charge_items.aggregate(total=models.Sum("amount"))["total"]
    return Decimal(total or 0)


def _money(amount: Decimal) -> str:
    """Thousands-grouped, 2dp — mirrors the quotation render seam's `_money`."""
    return f"{amount:,.2f}"


def _booking_base_total(booking: Booking) -> Decimal:
    """The snapshot total the guest-facing total sizes against.

    Mirrors `PaymentScheduler._booking_total`'s base extraction exactly:
    prefer `pricing_snapshot["total"]` (`str()`-coerced — JSON may yield a
    float), else `booking.balance_due`. There is deliberately no `booking.total`
    field; the snapshot is the locked-in breakdown captured at confirmation.
    """
    snapshot = getattr(booking, "pricing_snapshot", None) or {}
    if isinstance(snapshot, dict) and snapshot.get("total") is not None:
        return Decimal(str(snapshot["total"]))
    return Decimal(getattr(booking, "balance_due", Decimal("0")))


def booking_charge_breakdown(booking: Booking) -> dict[str, Any]:
    """Itemise a booking's charge lines for guest-facing comms.

    Decomposes the guest-facing total into the snapshot `base_amount` plus the
    signed `BookingChargeItem` lines (the legacy `VillaBookingDetail`
    itemisation), partitioned by sign into positive `charges` and negative
    `discounts` (a separate "Discounts" block, per the GAP-018 decision). The
    grand `total` replicates `PaymentScheduler._booking_total` byte-for-byte
    (flat 2dp quantize) so the email total equals the scheduled total.

    Money fields are pre-formatted strings (`_money`) the template interpolates
    directly. Lines come out in `pk` order (the model's `Meta.ordering`).

    The charge sum is accumulated from the same single pass that builds the
    lines rather than via `charges_total_for`: that keeps the builder
    prefetch-cache-friendly (`charge_items.aggregate(...)` would bypass a
    `prefetch_related` and re-query per booking — the N+1 the reminder-batch
    callers prefetch to avoid). The result is identical (both are `Σ amount`).
    """
    base = _booking_base_total(booking)
    charges: list[dict[str, str]] = []
    discounts: list[dict[str, str]] = []
    charges_sum = Decimal("0")
    for item in booking.charge_items.all():
        charges_sum += item.amount
        bucket = charges if item.amount > 0 else discounts
        bucket.append({"label": item.label, "amount": _money(item.amount)})
    total = (base + charges_sum).quantize(Decimal("0.01"))
    return {
        "currency": booking.currency.code,
        "base_amount": _money(base),
        "charges": charges,
        "discounts": discounts,
        "total": _money(total),
    }


def effective_commission_for(booking: Booking) -> dict[str, Any] | None:
    """Resolve the booking property's effective commission config.

    Tolerates a missing `PropertyFinance` row (legacy/imported data) by
    returning None; any other failure is a real bug and propagates.
    """
    from properties.models import PropertyFinance

    prop = booking.property
    if prop is None:
        return None
    try:
        finance = prop.finance
    except PropertyFinance.DoesNotExist:
        return None
    return finance.effective_commission()


class OwnerEffect(NamedTuple):
    """How a bookings' charge lines move the owner statement."""

    commission_on_charges: Decimal
    owner_delta: Decimal


def owner_effect(
    charges_total: Decimal,
    calculation_type: str | None,
    commission_amount: Decimal | None,
) -> OwnerEffect:
    """Split `charges_total` between agency commission and owner net.

    PERCENT commission skims its percentage off every charge (credits are
    symmetric — owner and agency share a credit by the same split). FIXED
    commission never moves with charges, so they flow to the owner in
    full; so do charges on properties with no commission configured.
    Charges are entered gross/tax-inclusive — tax is never recomputed.
    """
    if not charges_total:
        return OwnerEffect(ZERO, ZERO)
    if calculation_type == CommissionCalcType.PERCENT.value and commission_amount is not None:
        commission = (charges_total * commission_amount / Decimal("100")).quantize(Decimal("0.01"))
        return OwnerEffect(commission, charges_total - commission)
    return OwnerEffect(ZERO, charges_total)


def _snapshot_fields(item: BookingChargeItem) -> dict[str, Any]:
    """The before/after payload BookingEvent meta carries per mutation."""
    return {"label": item.label, "amount": f"{item.amount:.2f}", "notes": item.notes}


class ChargeItemService:
    """Create / update / delete manual charge lines, with the invariants."""

    @classmethod
    @transaction.atomic
    def create(
        cls,
        booking: Booking,
        *,
        label: str,
        amount: Decimal,
        currency: Currency | None = None,
        notes: str = "",
        actor: Any = None,
    ) -> BookingChargeItem:
        from reservations.models import BookingChargeItem

        booking = cls._lock_and_gate(booking)
        currency = cls._resolve_currency(booking, currency)
        cls._check_total(booking, delta=amount)
        item = BookingChargeItem.objects.create(
            booking=booking,
            label=label,
            amount=amount,
            currency=currency,
            notes=notes,
        )
        cls._write_event(booking, item, actor=actor, action="created", before=None)
        return item

    @classmethod
    @transaction.atomic
    def update(
        cls,
        item: BookingChargeItem,
        *,
        actor: Any = None,
        **fields: Any,
    ) -> BookingChargeItem:
        booking = cls._lock_and_gate(item.booking)
        if "currency" in fields:
            fields["currency"] = cls._resolve_currency(booking, fields["currency"])
        before = _snapshot_fields(item)
        new_amount = fields.get("amount", item.amount)
        cls._check_total(booking, delta=new_amount - item.amount)
        for name, value in fields.items():
            setattr(item, name, value)
        item.save()
        cls._write_event(booking, item, actor=actor, action="updated", before=before)
        return item

    @classmethod
    @transaction.atomic
    def delete(cls, item: BookingChargeItem, *, actor: Any = None) -> None:
        booking = cls._lock_and_gate(item.booking)
        before = _snapshot_fields(item)
        cls._check_total(booking, delta=-item.amount)
        item_id = item.pk
        item.delete()
        cls._write_event(
            booking, None, actor=actor, action="deleted", before=before, item_id=item_id
        )

    # ------------------------------------------------------------------
    # Invariants
    # ------------------------------------------------------------------
    @staticmethod
    def _lock_and_gate(booking: Booking) -> Booking:
        """Row-lock the booking (serialises against concurrent charge edits
        and `modify_dates` re-pricing) and refuse non-active states.

        Pre-approval negotiation belongs on the quotation, and terminal
        bookings are closed books; CHECKED_IN stays writable because
        mid-stay extras are a core use case (legacy allowed any active
        booking).
        """
        from reservations.models import Booking

        booking = Booking.objects.select_for_update().get(pk=booking.pk)
        if booking.status not in ACTIVE_BOOKING_STATUSES:
            raise InvalidTransition(
                booking.status,
                booking.status,
                allowed=list(ACTIVE_BOOKING_STATUSES),
            )
        return booking

    @staticmethod
    def _resolve_currency(booking: Booking, currency: Currency | None) -> Currency:
        """Default to the booking's currency; a mismatched line is a money bug
        (the charges Σ assumes single-currency rows)."""
        if currency is None:
            return booking.currency
        if currency.pk != booking.currency_id:
            raise DomainValidationError(
                field_errors={"currency": ["Charge items must use the booking's currency."]}
            )
        return currency

    @staticmethod
    def _check_total(booking: Booking, *, delta: Decimal) -> None:
        """Refuse a write that would push `balance_due + Σcharges` negative.

        Computed live under the booking row lock, so two concurrent credits
        can't slip past the guard together.
        """
        current = charges_total_for(booking)
        if booking.balance_due + current + delta < 0:
            raise DomainValidationError(
                field_errors={"amount": ["This would make the booking total negative."]}
            )

    @staticmethod
    def _write_event(
        booking: Booking,
        item: BookingChargeItem | None,
        *,
        actor: Any,
        action: str,
        before: dict[str, Any] | None,
        item_id: int | None = None,
    ) -> None:
        charges_total = charges_total_for(booking)
        booking._write_event(
            actor=actor,
            reason=f"charge_item_{action}",
            meta={
                "charge_item_id": item.pk if item is not None else item_id,
                "action": action,
                "before": before,
                "after": _snapshot_fields(item) if item is not None else None,
                "charges_total": f"{charges_total:.2f}",
            },
        )
