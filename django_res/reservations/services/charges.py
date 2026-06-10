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
from rest_framework.exceptions import ValidationError

from core.exceptions import InvalidTransition
from properties.enums import CommissionCalcType
from reservations.enums import ACTIVE_BOOKING_STATUSES

if TYPE_CHECKING:
    from pricing.models import Currency
    from reservations.models import Booking, BookingChargeItem

ZERO = Decimal("0.00")


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
            raise ValidationError({"currency": "Charge items must use the booking's currency."})
        return currency

    @staticmethod
    def _check_total(booking: Booking, *, delta: Decimal) -> None:
        """Refuse a write that would push `balance_due + Σcharges` negative.

        Computed live under the booking row lock, so two concurrent credits
        can't slip past the guard together.
        """
        current = booking.charge_items.aggregate(total=models.Sum("amount"))["total"] or Decimal(
            "0"
        )
        if booking.balance_due + current + delta < 0:
            raise ValidationError({"amount": "This would make the booking total negative."})

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
        charges_total = booking.charge_items.aggregate(total=models.Sum("amount"))[
            "total"
        ] or Decimal("0")
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
