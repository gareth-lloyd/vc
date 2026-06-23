"""`SecurityDepositService` — coordinates the `SecurityDeposit` workflow.

Owns the state-machine transitions, permission shape and the creation of
downstream `Payment(purpose=SECURITY_DEPOSIT)` rows that record the
gateway transactions. The model itself never talks to the gateway.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import structlog
from django.db import transaction
from django.utils import timezone

from core.exceptions import DomainValidationError, InvalidSecurityDepositKind
from core.locking import refresh_locked
from core.logging.operations import log_operation
from payments.enums import (
    ACTIVE_PAYMENT_STATUSES,
    TERMINAL_SD_STATUSES,
    EventSource,
    PaymentMethod,
    PaymentProvider,
    PaymentPurpose,
    PaymentStatus,
    SecurityDepositKind,
    SecurityDepositStatus,
)
from payments.models.payment import Payment
from payments.models.security_deposit import SecurityDeposit
from pricing.services.currency import quantise_money
from properties.enums import SecurityDepositCalcType, SecurityDepositPaymentMethod

if TYPE_CHECKING:
    from reservations.models import DamageClaim

logger = structlog.get_logger(__name__)


class SecurityDepositService:
    """Service-layer façade over the SecurityDeposit state machine."""

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------
    @classmethod
    def create_for_booking(cls, booking: Any) -> SecurityDeposit | None:
        """Open an SD workflow row at booking creation if the policy requires it.

        Returns the new `SecurityDeposit` row, or `None` if no SD is required
        by the property's `SecurityDepositPolicy`.
        """
        # Idempotent on the booking: a re-entry (signal re-fire, retry) must
        # return the existing row, never open a second one — two active rows
        # would break the one-active-SECURITY_DEPOSIT-per-booking invariant
        # (BUG-006). The booking FK is the natural idempotency key.
        existing = SecurityDeposit.objects.filter(booking=booking).first()
        if existing is not None:
            return existing

        finance = getattr(booking.property, "finance", None)
        if finance is None:
            return None
        policy = finance.effective_security_deposit_policy()
        if not policy.get("required"):
            return None

        amount = cls._size_sd(booking=booking, policy=policy)
        if amount <= 0:
            return None

        kind = cls._kind_from_policy_method(policy.get("payment_method"))
        initial_status = (
            SecurityDepositStatus.AWAITING_DETAILS.value
            if kind == SecurityDepositKind.PRE_AUTH_HOLD.value
            else SecurityDepositStatus.AWAITING_BT.value
        )

        due_at = cls._due_at(
            booking,
            days_before=policy.get("days_due_before_arrival"),
        )
        release_after = policy.get("days_refunded_after_departure")
        release_for = cls._release_scheduled_for(
            booking,
            days_after=release_after,
        )

        sd = SecurityDeposit.objects.create(
            booking=booking,
            kind=kind,
            amount=quantise_money(amount, booking.currency),
            currency=booking.currency,
            status=initial_status,
            due_at=due_at,
            release_after_departure_days=release_after,
            release_scheduled_for=release_for,
        )
        logger.info(
            "security_deposit.created",
            security_deposit_id=sd.pk,
            booking_id=booking.pk,
            kind=kind,
            amount=str(amount),
            currency=booking.currency.code,
        )
        return sd

    @classmethod
    @transaction.atomic
    def resize_for_booking(cls, booking: Any) -> SecurityDeposit | None:
        """Resize a still-pre-charge SD when the booking total moves.

        Hooked on `booking_total_changed` (charge-item writes *and* the
        `modify_dates`/`modify_guests` endpoints), alongside the deposit/balance
        schedule resync — this is what makes a charge added *after* the SD row
        exists resize it (`PaymentScheduler.resync_for_booking` filters to
        DEPOSIT/BALANCE and never touches the SD).

        Only an SD that holds no money yet — AWAITING_DETAILS / AWAITING_BT —
        may be resized; once it is PRE_AUTHED/HELD the figure is committed at the
        provider, so a move is recorded as a deliberate skip event for operators
        rather than silently applied. Percent SDs re-derive against the same
        charges-inclusive total `create_for_booking` sized against; a fixed SD is
        unaffected by the move (recomputes to the same figure, no event). No
        SD → no-op.

        Atomic and row-locked like every `transition_to_*`: the candidate is
        re-read under `SELECT … FOR UPDATE` before any decision, so a concurrent
        `hold()`/`mark_paid()` that committed the figure at the provider between
        the unlocked lookup and here is seen (and skipped) rather than clobbered.
        """
        sd = (
            SecurityDeposit.objects.filter(booking=booking)
            .exclude(status__in=TERMINAL_SD_STATUSES)
            .first()
        )
        if sd is None:
            return None

        # Lock + re-read before deciding anything. The lookup above is unlocked,
        # so the status/amount it returned may already be stale; every other SD
        # mutator takes this lock before its guard (`SecurityDeposit._transition`)
        # and resize must too, or it can overwrite a provider-committed amount.
        refresh_locked(sd)

        finance = getattr(booking.property, "finance", None)
        if finance is None:
            return sd
        policy = finance.effective_security_deposit_policy()
        if not policy.get("required"):
            return sd

        new_amount = quantise_money(cls._size_sd(booking=booking, policy=policy), booking.currency)
        if new_amount == sd.amount:
            # The figure didn't move (a fixed SD, or a signal that left the
            # total unchanged) — nothing to apply and nothing worth recording.
            # Checked before the status guard so a settled SD does not accrue a
            # skip event on every booking_total_changed that is a no-op for it.
            return sd

        if sd.status not in (
            SecurityDepositStatus.AWAITING_DETAILS.value,
            SecurityDepositStatus.AWAITING_BT.value,
        ):
            cls._write_sd_event(
                sd,
                kind="RESIZE_SKIPPED",
                status=sd.status,
                amount=str(sd.amount),
                would_be=str(new_amount),
                reason="not_pre_charge",
            )
            logger.info(
                "security_deposit.resize_skipped",
                security_deposit_id=sd.pk,
                booking_id=booking.pk,
                sd_status=sd.status,
                would_be=str(new_amount),
                reason="not_pre_charge",
            )
            return sd

        if new_amount <= 0:
            # A credit drove the recomputed figure to/under zero. The amount>0
            # constraint forbids writing it, so the row stays at its current
            # figure — but it is now overstated, so record the skip rather than
            # returning mute (mirrors the schedule resync's residual write).
            cls._write_sd_event(
                sd,
                kind="RESIZE_SKIPPED",
                status=sd.status,
                amount=str(sd.amount),
                would_be=str(new_amount),
                reason="non_positive_total",
            )
            logger.warning(
                "security_deposit.resize_skipped",
                security_deposit_id=sd.pk,
                booking_id=booking.pk,
                sd_status=sd.status,
                would_be=str(new_amount),
                reason="non_positive_total",
            )
            return sd

        old_amount = sd.amount
        sd.amount = new_amount
        sd.save(update_fields=["amount", "updated_at"])
        cls._write_sd_event(
            sd, kind="RESIZE", from_amount=str(old_amount), to_amount=str(new_amount)
        )
        logger.info(
            "security_deposit.resized",
            security_deposit_id=sd.pk,
            booking_id=booking.pk,
            from_amount=str(old_amount),
            to_amount=str(new_amount),
            currency=booking.currency.code,
        )
        return sd

    # ------------------------------------------------------------------
    # Transitions
    # ------------------------------------------------------------------
    @classmethod
    @transaction.atomic
    def hold(
        cls,
        sd: SecurityDeposit,
        *,
        gateway_response: dict[str, Any],
        actor: Any = None,
    ) -> SecurityDeposit:
        """Pre-auth path: AWAITING_DETAILS → PRE_AUTHED.

        Creates a `Payment(purpose=SECURITY_DEPOSIT, status=SUCCEEDED)`
        recording the pre-auth charge.
        """
        # Kind guard above the log_operation block — a wrong-kind call is an
        # expected rejection (→ 409 via the canonical handler), not an
        # operation failure worth a `.failed` traceback (BUG-011).
        if sd.kind != SecurityDepositKind.PRE_AUTH_HOLD.value:
            raise InvalidSecurityDepositKind(
                f"SD {sd.reference}: :hold only valid for PRE_AUTH_HOLD kind"
            )
        hold_expires_at = gateway_response.get("hold_expires_at")
        provider = gateway_response.get("provider", PaymentProvider.FLYWIRE.value)
        provider_reference = gateway_response.get("provider_reference", "")

        with log_operation(
            "security_deposit.hold",
            logger=logger,
            security_deposit_id=sd.pk,
            booking_id=sd.booking_id,
            amount=str(sd.amount),
            currency=sd.currency.code,
        ):
            Payment.objects.create(
                booking=sd.booking,
                purpose=PaymentPurpose.SECURITY_DEPOSIT.value,
                status=PaymentStatus.SUCCEEDED.value,
                amount=sd.amount,
                currency=sd.currency,
                provider=provider,
                provider_reference=provider_reference,
                payment_method=PaymentMethod.CARD.value,
                settled_at=timezone.now(),
                meta={"security_deposit_id": sd.pk, "kind": "PRE_AUTH_HOLD"},
            )

            if hold_expires_at:
                sd.hold_expires_at = hold_expires_at
                sd.save(update_fields=["hold_expires_at", "updated_at"])

            return sd.transition_to_pre_authed(actor=actor)

    @classmethod
    @transaction.atomic
    def mark_paid(
        cls,
        sd: SecurityDeposit,
        *,
        amount: Decimal,
        paid_at: datetime,
        method: str,
        reference: str,
        actor: Any = None,
    ) -> SecurityDeposit:
        """BT-refundable path: AWAITING_BT → HELD.

        Records a manual bank-transfer receipt by creating a
        `Payment(provider=MANUAL_BANK_TRANSFER, status=SUCCEEDED)`.
        """
        if sd.kind != SecurityDepositKind.BT_REFUNDABLE.value:
            raise InvalidSecurityDepositKind(
                f"SD {sd.reference}: :mark-paid only valid for BT_REFUNDABLE kind"
            )

        with log_operation(
            "security_deposit.mark_paid",
            logger=logger,
            security_deposit_id=sd.pk,
            booking_id=sd.booking_id,
            amount=str(amount),
            currency=sd.currency.code,
            method=method,
        ):
            Payment.objects.create(
                booking=sd.booking,
                purpose=PaymentPurpose.SECURITY_DEPOSIT.value,
                status=PaymentStatus.SUCCEEDED.value,
                amount=quantise_money(amount, sd.currency),
                currency=sd.currency,
                provider=PaymentProvider.MANUAL_BANK_TRANSFER.value,
                provider_reference=reference,
                payment_method=method,
                settled_at=paid_at,
                meta={"security_deposit_id": sd.pk, "kind": "BT_HELD"},
            )

            return sd.transition_to_held(actor=actor)

    @classmethod
    @transaction.atomic
    def release(cls, sd: SecurityDeposit, *, actor: Any = None) -> SecurityDeposit:
        """PRE_AUTHED → RELEASED   (void hold via gateway)
        HELD       → REFUNDED   (open & execute Refund)
        """
        with log_operation(
            "security_deposit.release",
            logger=logger,
            security_deposit_id=sd.pk,
            booking_id=sd.booking_id,
            amount=str(sd.amount),
            currency=sd.currency.code,
            kind=sd.kind,
        ):
            if sd.kind == SecurityDepositKind.BT_REFUNDABLE.value:
                # BT release delegates to the Refund workflow so separation of
                # duties applies uniformly. We open the Refund here; in
                # production the operator-facing flow would `:approve` and
                # `:execute` separately.
                from payments.enums import (
                    RefundMethod,
                    RefundPurposeTrack,
                    RefundReasonCode,
                )
                from payments.services.refund import RefundService

                inbound_payment = (
                    Payment.objects.filter(
                        booking=sd.booking,
                        purpose=PaymentPurpose.SECURITY_DEPOSIT.value,
                        status=PaymentStatus.SUCCEEDED.value,
                        provider=PaymentProvider.MANUAL_BANK_TRANSFER.value,
                    )
                    .order_by("-settled_at")
                    .first()
                )
                RefundService.request(
                    booking=sd.booking,
                    amount=sd.amount,
                    currency=sd.currency,
                    purpose_track=RefundPurposeTrack.SECURITY_DEPOSIT.value,
                    reason_code=RefundReasonCode.SECURITY_DEPOSIT_RELEASE.value,
                    method=RefundMethod.MANUAL_BANK_TRANSFER.value,
                    against_payment=inbound_payment,
                    requested_by=actor,
                    security_deposit=sd,
                )
                # No approve/execute step here — the calling task or operator
                # workflow drives those (and bears the audit). We surface the
                # transition on the SD itself so callers can observe the
                # lifecycle.
            return sd.transition_to_released(actor=actor)

    @classmethod
    @transaction.atomic
    def claim(
        cls,
        sd: SecurityDeposit,
        *,
        damage_claim: Any,
        captured_amount: Decimal,
        actor: Any = None,
    ) -> SecurityDeposit:
        """PRE_AUTHED → CAPTURED          (gateway capture)
        HELD       → PARTIALLY_REFUNDED (Refund for the residual)

        `damage_claim` may arrive as a `DamageClaim` instance (internal callers)
        or a raw PK (the operator API passes `request.data['damage_claim']`).
        It is resolved to a real, booking-matched row up front so a bad PK is a
        clean 400 rather than the DB FK constraint raising a 500 mid-capture.
        """
        with log_operation(
            "security_deposit.claim",
            logger=logger,
            security_deposit_id=sd.pk,
            booking_id=sd.booking_id,
            amount=str(sd.amount),
            captured_amount=str(captured_amount),
            currency=sd.currency.code,
            kind=sd.kind,
        ):
            # Resolve inside the operation block so a rejected claim still emits
            # the `.failed` event (the logging triple covers this fallible read).
            damage_claim = cls._resolve_damage_claim(sd, damage_claim)
            if sd.kind == SecurityDepositKind.PRE_AUTH_HOLD.value:
                # The capture supersedes the pre-auth hold: settle the held
                # authorisation into a captured charge. Retire the still-active
                # hold Payment first so only the capture occupies the
                # one-active-SECURITY_DEPOSIT-per-booking slot (BUG-006) —
                # leaving both SUCCEEDED would double-count the deposit on the
                # ledger.
                cls._supersede_active_hold(sd, actor=actor)
                Payment.objects.create(
                    booking=sd.booking,
                    purpose=PaymentPurpose.SECURITY_DEPOSIT.value,
                    status=PaymentStatus.SUCCEEDED.value,
                    amount=captured_amount,
                    currency=sd.currency,
                    provider=PaymentProvider.FLYWIRE.value,
                    payment_method=PaymentMethod.CARD.value,
                    settled_at=timezone.now(),
                    meta={"security_deposit_id": sd.pk, "kind": "CAPTURE"},
                )
                return sd.transition_to_captured(
                    captured_amount=captured_amount,
                    damage_claim=damage_claim,
                    actor=actor,
                )
            return sd.transition_to_partially_refunded(
                captured_amount=captured_amount,
                damage_claim=damage_claim,
                actor=actor,
            )

    @staticmethod
    def _resolve_damage_claim(sd: SecurityDeposit, damage_claim: Any) -> DamageClaim | None:
        """Coerce an instance-or-PK-or-None into a booking-matched DamageClaim.

        `None` is allowed (a capture may not yet carry a formal claim — the
        mandatory-claim gating is part of the deferred approval workflow). A
        provided value must resolve to an existing claim on the *same booking*
        as the deposit; otherwise `DomainValidationError` (400), never the FK
        constraint's IntegrityError (500).
        """
        from reservations.models import DamageClaim

        if damage_claim is None or isinstance(damage_claim, DamageClaim):
            claim = damage_claim
        else:
            try:
                claim = DamageClaim.objects.get(pk=damage_claim)
            except (DamageClaim.DoesNotExist, ValueError, TypeError):
                # DoesNotExist: no such row. ValueError/TypeError: the JSON value
                # (`request.data['damage_claim']`) wasn't a coercible PK at all
                # (e.g. "abc", a list) — still a 400, never a 500.
                raise DomainValidationError(
                    f"No DamageClaim with id {damage_claim!r}.",
                    field_errors={"damage_claim": ["No such damage claim."]},
                ) from None
        if claim is not None and claim.booking_id != sd.booking_id:
            raise DomainValidationError(
                "DamageClaim belongs to a different booking than the deposit.",
                field_errors={"damage_claim": ["Claim is for a different booking."]},
            )
        return claim

    @classmethod
    @transaction.atomic
    def expire(cls, sd: SecurityDeposit, *, actor: Any = None) -> SecurityDeposit:
        """PRE_AUTHED → EXPIRED   (system: gateway voided hold)
        AWAITING_BT → FAILED    (system: BT never arrived by due_at)
        """
        with log_operation(
            "security_deposit.expire",
            logger=logger,
            security_deposit_id=sd.pk,
            booking_id=sd.booking_id,
            kind=sd.kind,
        ):
            return sd.transition_to_expired(actor=actor)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _write_sd_event(sd: SecurityDeposit, *, kind: str, **meta: Any) -> None:
        """Append a non-transitional (status-unchanged) audit row to the SD's
        PaymentEvent stream — used by the resize/skip bookkeeping above so the
        un/applied total change is visible on the SD timeline, not just in logs.
        """
        from payments.models.payment_event import PaymentEvent

        PaymentEvent.objects.create(
            security_deposit=sd,
            kind=kind,
            source=EventSource.SYSTEM.value,
            meta=meta,
        )

    @staticmethod
    def _supersede_active_hold(sd: SecurityDeposit, *, actor: Any = None) -> None:
        """Retire the still-active pre-auth hold Payment for `sd`.

        The capture that follows mints its own SECURITY_DEPOSIT row; the hold
        authorisation it settles must leave the active set so only one active
        SECURITY_DEPOSIT row per booking survives (BUG-006) and the ledger
        doesn't double-count. CANCELLED fires no payment signal, so retiring
        the hold here has no downstream side effects.
        """
        hold = (
            Payment.objects.filter(
                booking=sd.booking,
                purpose=PaymentPurpose.SECURITY_DEPOSIT.value,
                status__in=ACTIVE_PAYMENT_STATUSES,
                meta__security_deposit_id=sd.pk,
            )
            .order_by("-id")
            .first()
        )
        if hold is not None:
            hold.transition_to(
                PaymentStatus.CANCELLED.value,
                source=EventSource.SYSTEM.value,
                actor=actor,
                kind="SUPERSEDED_BY_CAPTURE",
                reason="Pre-auth hold superseded by capture",
            )

    @staticmethod
    def _kind_from_policy_method(method: str | None) -> str:
        """Map a `SecurityDepositPaymentMethod` value to a `SecurityDepositKind`."""
        if method == SecurityDepositPaymentMethod.BANK_TRANSFER.value:
            return SecurityDepositKind.BT_REFUNDABLE.value
        # `card_hold` and `card_charge` both flow through the pre-auth path
        # for v1; differentiation lands when CARD_CHARGE captures up-front.
        return SecurityDepositKind.PRE_AUTH_HOLD.value

    @staticmethod
    def _size_sd(*, booking: Any, policy: dict[str, Any]) -> Decimal:
        amount = policy.get("amount")
        if amount is None:
            return Decimal("0.00")
        value = Decimal(str(amount))
        if policy.get("calculation_type") == SecurityDepositCalcType.PERCENT.value:
            # Late import — `PaymentScheduler` lives in another module in
            # this package and late-imports this one (create_for_booking).
            from payments.services.payment_scheduler import PaymentScheduler

            # The same charges-inclusive total the deposit/balance schedule
            # sizes against — a percent SD on bare `balance_due` would
            # silently undersize once manual charges exist.
            base = PaymentScheduler._booking_total(booking)
            return (base * value / Decimal(100)).quantize(Decimal("0.01"))
        return value.quantize(Decimal("0.01"))

    @staticmethod
    def _due_at(booking: Any, *, days_before: int | None) -> datetime | None:
        if days_before is None:
            return None
        date_from = getattr(booking, "date_from", None)
        if date_from is None:
            return None
        target = date_from - timedelta(days=int(days_before))
        return datetime.combine(
            target,
            datetime.min.time(),
            tzinfo=timezone.get_current_timezone(),
        )

    @staticmethod
    def _release_scheduled_for(booking: Any, *, days_after: int | None) -> Any:
        if days_after is None:
            return None
        date_to = getattr(booking, "date_to", None)
        if date_to is None:
            return None
        return date_to + timedelta(days=int(days_after))
