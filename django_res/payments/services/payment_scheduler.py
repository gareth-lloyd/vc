"""`PaymentScheduler` — generates the per-booking payment row schedule.

Called at `Booking` creation. Reads the effective payment-schedule and
security-deposit policy from `PropertyFinance` (with `GroupFinance`
fallback), sizes each row, and writes them as `Payment` rows in PENDING.
The security-deposit workflow row, if required, is opened by
`SecurityDepositService.create_for_booking()` (delegated here so the
scheduler stays focused on the deposit/interim/balance track).
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from payments.enums import PaymentPurpose, PaymentStatus
from payments.models.payment import Payment
from properties.enums import DepositCalcType

logger = logging.getLogger(__name__)

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
        # Late import — `SecurityDepositService` lives in another module in
        # this package and we don't want a circular import at module load.
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
                "PaymentScheduler: booking %s on property %s has no PropertyFinance; "
                "no payment schedule created",
                getattr(booking, "pk", None),
                getattr(booking, "property_id", None),
            )
            return []
        schedule = finance.effective_payment_schedule()
        currency = booking.currency
        total = cls._booking_total(booking)
        balance_due_at = cls._coerce_due_at(getattr(booking, "balance_due_at", None))

        to_create: list[Payment] = []

        deposit_amount = cls._calc_amount(
            calculation_type=schedule.get("deposit_calculation_type"),
            amount=schedule.get("deposit_amount"),
            base=total,
        )
        if schedule.get("deposit_required") and deposit_amount > 0:
            to_create.append(
                Payment(
                    booking=booking,
                    purpose=PaymentPurpose.DEPOSIT.value,
                    status=PaymentStatus.PENDING.value,
                    amount=deposit_amount,
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
        balance_amount = max(
            Decimal("0"),
            total - deposit_amount,
        ).quantize(Decimal("0.01"))
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

        # `bulk_create` skips `save()` — assign each reference up-front.
        # We need distinct references across rows in the same call, which
        # the millisecond suffix can't guarantee; mix in a UUID-derived tail
        # so collisions inside a single batch are impossible.
        import uuid

        from django.utils import timezone as dj_tz

        year = dj_tz.now().year
        for row in to_create:
            row.reference = f"P-{year}-{uuid.uuid4().hex[:10].upper()}"

        created = Payment.objects.bulk_create(to_create)

        # The SD workflow is independent of the deposit/balance ledger rows
        # but is conceptually part of the schedule the operator sees.
        SecurityDepositService.create_for_booking(booking)

        return list(created)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _booking_total(booking: Any) -> Decimal:
        """Extract the total amount the schedule sizes against.

        Prefers `booking.pricing_snapshot["total"]` (the locked-in JSON
        breakdown captured at confirmation time); falls back to
        `booking.balance_due` when no snapshot is set yet.
        """
        snapshot = getattr(booking, "pricing_snapshot", None) or {}
        if isinstance(snapshot, dict) and snapshot.get("total") is not None:
            return Decimal(str(snapshot["total"])).quantize(Decimal("0.01"))
        balance = getattr(booking, "balance_due", Decimal("0"))
        return Decimal(balance).quantize(Decimal("0.01"))

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
