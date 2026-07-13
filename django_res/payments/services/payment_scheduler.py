"""`PaymentScheduler` — generates the per-booking payment row schedule.

Called at `Booking` creation. Reads the effective payment-schedule and
security-deposit policy from `PropertyFinance` (NULLs resolve to the policy
floor), sizes each row, and writes them as `Payment` rows in PENDING.
The security-deposit workflow row, if required, is opened by
`SecurityDepositService.create_for_booking()` (delegated here so the
scheduler stays focused on the deposit/interim/balance track).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

import structlog
from django.db import transaction
from django.utils import timezone

from core.logging.operations import log_operation
from payments.enums import PaymentPurpose, PaymentStatus
from payments.models.payment import Payment
from pricing.services.currency import quantise_money
from properties.enums import DepositCalcType
from reservations.services.charges import booking_total

logger = structlog.get_logger(__name__)

# The schedule rows this service owns. The idempotency check is scoped to these
# purposes so that an unrelated Payment on the booking (a SECURITY_DEPOSIT
# hold, a REFUND, an ad-hoc charge) can't masquerade as "already scheduled" and
# suppress the deposit/balance schedule.
_SCHEDULE_PURPOSES = (PaymentPurpose.DEPOSIT.value, PaymentPurpose.BALANCE.value)


class PaymentScheduler:
    """Build the deposit/interim/balance row schedule for a fresh booking."""

    @classmethod
    @transaction.atomic
    def create_for_booking(cls, booking: Any) -> list[Payment]:
        """Create PENDING Payment rows for the booking's payment schedule.

        Returns the list of Payment rows created (deposit, optional interim,
        balance). The SecurityDeposit row is created separately via
        `SecurityDepositService.create_for_booking()`.

        Atomic: the deposit/balance rows and the SecurityDeposit row are
        written all-or-nothing, so a failure part-way never leaves a booking
        with a deposit row but no balance row (or vice versa).
        """
        from payments.services.security_deposit import SecurityDepositService

        # Idempotent: the scheduler is reachable from the booking-creation
        # signal and from explicit callers, so a re-entry (signal re-fire, a
        # webhook retry, an operator double-submit) must return the existing
        # rows rather than mint a second deposit/balance set. A `Booking`
        # naturally owns its schedule, so the FK (scoped to the schedule
        # purposes) is the idempotency key.
        existing = list(Payment.objects.filter(booking=booking, purpose__in=_SCHEDULE_PURPOSES))
        if existing:
            return existing

        # A property with no `PropertyFinance` row has no schedule to size
        # against. Degrade gracefully (no payments) rather than raising — the
        # signal fires on every booking creation, so a financeless property
        # must not break booking creation. Mirrors `Property.balance_due_at`'s
        # `getattr(self, "finance", None)` guard. Log it: in production every
        # property should resolve a finance row, so a miss is a misconfiguration
        # (a booking that can collect no money) worth surfacing, not swallowing.
        finance = getattr(booking.property, "finance", None)
        if finance is None:
            logger.warning(
                "payment.schedule_skipped",
                reason="no_property_finance",
                booking_id=getattr(booking, "pk", None),
                property_id=getattr(booking, "property_id", None),
            )
            return []
        schedule = finance.effective_payment_schedule()
        currency = booking.currency
        total = booking_total(booking)
        balance_due_at = cls._coerce_due_at(getattr(booking, "balance_due_at", None))

        to_create: list[Payment] = []

        deposit_amount = cls._calc_amount(
            calculation_type=schedule.get("deposit_calculation_type"),
            amount=schedule.get("deposit_amount"),
            base=total,
        )
        # Quantise once and derive the balance from the quantised value, so
        # `deposit_saved + balance_saved == total` holds by construction even
        # for non-2dp currencies at exact-half splits. The balance subtracts
        # this UNCONDITIONALLY (matching prior behaviour) — even when no deposit
        # row is created (deposit_required False / deposit_amount 0), the same
        # quantised value is subtracted as before, only now quantised.
        quantised_deposit = quantise_money(deposit_amount, currency)
        if schedule.get("deposit_required") and deposit_amount > 0:
            to_create.append(
                Payment(
                    booking=booking,
                    purpose=PaymentPurpose.DEPOSIT.value,
                    status=PaymentStatus.PENDING.value,
                    amount=quantised_deposit,
                    currency=currency,
                    due_at=timezone.now(),
                )
            )

        interim_amount = cls._calc_amount(
            calculation_type=schedule.get("interim_calculation_type"),
            amount=schedule.get("interim_amount"),
            base=total,
        )
        # NOTE: interim instalments aren't a first-class `PaymentPurpose` yet
        # (the active-per-purpose unique constraint covers only DEPOSIT and
        # BALANCE). Until INTERIM lands as its own purpose, the interim
        # amount is rolled into the BALANCE row — the scheduler still
        # reports it so callers can render a richer schedule view.
        _ = interim_amount  # placeholder for future INTERIM purpose

        # Until INTERIM is its own purpose, the full remaining balance owes on
        # the BALANCE row regardless of whether the schedule split it.
        balance_amount = quantise_money(
            max(Decimal("0"), total - quantised_deposit),
            currency,
        )
        to_create.append(
            Payment(
                booking=booking,
                purpose=PaymentPurpose.BALANCE.value,
                status=PaymentStatus.PENDING.value,
                amount=balance_amount,
                currency=currency,
                due_at=balance_due_at,
            )
        )

        # `bulk_create` skips `save()`, but `Payment.reference` is stamped by a
        # Postgres sequence wired as the column's `db_default` (BUG-007), so the
        # database assigns a distinct reference on every insert path. Postgres
        # returns the generated value via `INSERT ... RETURNING`, so the rows
        # come back with `reference` already populated — no re-fetch needed.
        created = Payment.objects.bulk_create(to_create)

        # The SD workflow is independent of the deposit/balance ledger rows
        # but is conceptually part of the schedule the operator sees.
        SecurityDepositService.create_for_booking(booking)

        return list(created)

    @classmethod
    @transaction.atomic
    def resync_for_booking(cls, booking: Any) -> None:
        """Resize the unsettled DEPOSIT/BALANCE rows after the total moved.

        Legacy regenerated the whole schedule on every booking modify; the
        rebuild equivalent recomputes from scratch (idempotent) but only
        ever rewrites PENDING rows. SUCCEEDED money is history; PROCESSING
        is mid-flight at the provider, so both are treated as committed at
        their current amount. Reached via the `booking_total_changed`
        receiver in `payments.signals`.

        When the new total can't be absorbed (everything settled, or a
        credit dropped the total below committed money), PENDING rows clamp
        at 0 and the residual is logged *and* written to a BookingEvent so
        operators see it on the Timeline; collecting or refunding it stays
        an explicit operator action.
        """
        rows = list(
            Payment.objects.select_for_update()
            .filter(booking=booking, purpose__in=_SCHEDULE_PURPOSES)
            .order_by("pk")
        )
        if not rows:
            # No schedule yet (pre-AWAITING_DEPOSIT or financeless property)
            # — `create_for_booking` sizes against the charges when it runs.
            return

        total = booking_total(booking)
        with log_operation(
            "payment.schedule_resync",
            logger=logger,
            booking_id=booking.pk,
            total=str(total),
        ) as ctx:
            pending = [r for r in rows if r.status == PaymentStatus.PENDING.value]
            committed = sum(
                (
                    r.amount
                    for r in rows
                    if r.status in (PaymentStatus.PROCESSING.value, PaymentStatus.SUCCEEDED.value)
                ),
                Decimal("0"),
            )

            remaining = max(Decimal("0"), total - committed)
            deposit = next((r for r in pending if r.purpose == PaymentPurpose.DEPOSIT.value), None)
            if deposit is not None:
                finance = getattr(booking.property, "finance", None)
                schedule = finance.effective_payment_schedule() if finance else {}
                deposit.amount = quantise_money(
                    min(
                        remaining,
                        cls._calc_amount(
                            calculation_type=schedule.get("deposit_calculation_type"),
                            amount=schedule.get("deposit_amount"),
                            base=total,
                        ),
                    ),
                    booking.currency,
                )
                deposit.save(update_fields=["amount", "updated_at"])
                remaining -= deposit.amount

            balance = next((r for r in pending if r.purpose == PaymentPurpose.BALANCE.value), None)
            if balance is not None:
                balance.amount = quantise_money(remaining, booking.currency)
                balance.save(update_fields=["amount", "updated_at"])
                remaining = Decimal("0")

            residual = quantise_money(
                total - committed - sum((r.amount for r in pending), Decimal("0")),
                booking.currency,
            )
            if residual:
                ctx["residual"] = str(residual)
                # `payments > reservations` is a clean downward edge, so the
                # Timeline write happens right here rather than via a signal.
                booking._write_event(
                    source="system",
                    reason="payment_schedule_residual",
                    meta={"residual": str(residual), "total": str(total)},
                )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _calc_amount(
        *,
        calculation_type: str | None,
        amount: Decimal | float | int | None,
        base: Decimal,
    ) -> Decimal:
        if amount is None:
            return Decimal("0.00")
        value = Decimal(str(amount))
        if calculation_type == DepositCalcType.PERCENT.value:
            return (base * value / Decimal(100)).quantize(Decimal("0.01"))
        # FIXED or unknown → take the value verbatim.
        return value.quantize(Decimal("0.01"))

    @staticmethod
    def _coerce_due_at(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        # `date` → midnight UTC, just for a deterministic timestamp.
        return datetime.combine(value, datetime.min.time(), tzinfo=timezone.get_current_timezone())
