"""`RefundService` — coordinates the `Refund` workflow.

State transitions live on the `Refund` model itself (via `_transition`);
this service layers business policy on top: who may approve, when a
gateway-bound `Payment(purpose=REFUND, status=PROCESSING)` row is created,
and how a refund derives from a cancellation.

Permission shape: each transition consults `actor.has_perm(...)` for the
relevant Django permission code. Tests skip permission scaffolding by
passing `actor=None`, in which case the service grants the action (system
flow). The separation-of-duties guardrail is enforced both in this service
(`payments.refund.self_approve`) and at the DB (`CheckConstraint` on
`refund_separation_of_duties`).
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from core.idempotency import find_by_meta_key, stamp_meta
from payments.enums import (
    PaymentPurpose,
    PaymentStatus,
    RefundMethod,
    RefundPurposeTrack,
    RefundReasonCode,
    RefundStatus,
)
from payments.models.payment import Payment
from payments.models.refund import Refund

if TYPE_CHECKING:
    from payments.models.security_deposit import SecurityDeposit


PERM_APPROVE = "payments.approve_refund"
PERM_EXECUTE = "payments.execute_refund"
PERM_SELF_APPROVE = "payments.self_approve_refund"


def _actor_has_perm(actor: Any, perm: str) -> bool:
    """Return True if `actor` carries the named permission.

    A `None` actor is interpreted as a system caller and granted every
    action — service-layer permission checks gate user actions only.
    """
    if actor is None:
        return True
    has_perm = getattr(actor, "has_perm", None)
    if has_perm is None:
        return False
    return bool(has_perm(perm))


class RefundService:
    """Service-layer façade over the Refund state machine."""

    # ------------------------------------------------------------------
    # Open a new Refund
    # ------------------------------------------------------------------
    @classmethod
    @transaction.atomic
    def request(
        cls,
        *,
        booking: Any,
        amount: Decimal,
        currency: Any,
        purpose_track: str,
        reason_code: str,
        reason_notes: str = "",
        method: str = RefundMethod.ONLINE_GATEWAY.value,
        against_payment: Payment | None = None,
        requested_by: Any = None,
        security_deposit: SecurityDeposit | None = None,
        idempotency_key: str | None = None,
    ) -> Refund:
        """Open a refund in PENDING.

        Validates the cumulative refund total against
        `against_payment.amount` (if set) so partial-refund stacks can't
        over-refund.

        Pass `idempotency_key` from webhooks or operator UIs that may
        retry: a second `request(...)` with the same key + booking
        returns the original Refund untouched instead of double-opening.
        """
        existing = find_by_meta_key(
            Refund.objects.filter(booking=booking),
            idempotency_key,
        )
        if existing is not None:
            return existing

        if amount is None or Decimal(str(amount)) <= 0:
            raise ValueError("Refund amount must be positive")

        if against_payment is not None:
            already_refunded = Refund.objects.filter(
                against_payment=against_payment,
            ).exclude(
                status__in=(
                    RefundStatus.REJECTED.value,
                    RefundStatus.CANCELLED.value,
                    RefundStatus.FAILED.value,
                ),
            ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
            if (already_refunded + Decimal(str(amount))) > Decimal(against_payment.amount):
                raise ValueError(
                    "Cumulative refund amount exceeds the original Payment amount",
                )

        refund = Refund.objects.create(
            booking=booking,
            against_payment=against_payment,
            purpose_track=purpose_track,
            amount=Decimal(str(amount)),
            currency=currency,
            status=RefundStatus.PENDING.value,
            reason_code=reason_code,
            reason_notes=reason_notes,
            method=method,
            requested_by=requested_by,
            security_deposit=security_deposit,
            meta=stamp_meta(None, idempotency_key),
        )
        return refund

    # ------------------------------------------------------------------
    # Transitions
    # ------------------------------------------------------------------
    @classmethod
    @transaction.atomic
    def approve(cls, refund: Refund, *, actor: Any) -> Refund:
        """PENDING → APPROVED.

        Asserts `actor != refund.requested_by` unless the actor carries
        `payments.refund.self_approve`. The DB `CheckConstraint` floors the
        rule independently — service-layer checks fail fast with a
        readable error before the constraint trips.
        """
        if refund.status != RefundStatus.PENDING.value:
            raise ValueError(f"Refund {refund.reference}: cannot :approve from {refund.status!r}")
        if not _actor_has_perm(actor, PERM_APPROVE):
            raise PermissionError(f"actor {actor!r} missing {PERM_APPROVE!r} permission")
        if (
            actor is not None
            and refund.requested_by_id is not None
            and getattr(actor, "pk", None) == refund.requested_by_id
            and not _actor_has_perm(actor, PERM_SELF_APPROVE)
        ):
            raise PermissionError(
                f"Requester cannot self-approve a refund without {PERM_SELF_APPROVE!r}",
            )

        refund.approved_by = actor
        refund.approved_at = timezone.now()
        refund.save(update_fields=["approved_by", "approved_at", "updated_at"])
        return refund._transition(RefundStatus.APPROVED.value, actor=actor)

    @classmethod
    @transaction.atomic
    def reject(cls, refund: Refund, *, actor: Any, reason: str) -> Refund:
        if refund.status != RefundStatus.PENDING.value:
            raise ValueError(f"Refund {refund.reference}: cannot :reject from {refund.status!r}")
        if not _actor_has_perm(actor, PERM_APPROVE):
            raise PermissionError(f"actor {actor!r} missing {PERM_APPROVE!r} permission")
        refund.rejected_by = actor
        refund.rejected_at = timezone.now()
        refund.rejection_reason = reason
        refund.save(
            update_fields=[
                "rejected_by",
                "rejected_at",
                "rejection_reason",
                "updated_at",
            ]
        )
        return refund._transition(
            RefundStatus.REJECTED.value,
            actor=actor,
            reason=reason,
        )

    @classmethod
    @transaction.atomic
    def cancel(cls, refund: Refund, *, actor: Any) -> Refund:
        if refund.status not in (
            RefundStatus.PENDING.value,
            RefundStatus.APPROVED.value,
        ):
            raise ValueError(f"Refund {refund.reference}: cannot :cancel from {refund.status!r}")
        # Requester may cancel while PENDING; approver/permission-holder may
        # cancel while APPROVED.
        if refund.status == RefundStatus.APPROVED.value and not _actor_has_perm(
            actor, PERM_APPROVE
        ):
            raise PermissionError(f"actor missing {PERM_APPROVE!r} to cancel approved refund")
        refund.cancelled_at = timezone.now()
        refund.save(update_fields=["cancelled_at", "updated_at"])
        return refund._transition(RefundStatus.CANCELLED.value, actor=actor)

    @classmethod
    @transaction.atomic
    def execute(cls, refund: Refund, *, actor: Any) -> Refund:
        """APPROVED → EXECUTING.

        Creates one `Payment(purpose=REFUND, status=PROCESSING)` linked
        via `meta['refund_id']`. Would normally enqueue
        `process_refund.delay(refund.id)`; we just create the row here.

        Idempotent on `refund.pk`: a second `execute` call (e.g. a
        webhook retry) skips re-creating the outbound `Payment` if one
        already exists for this refund, and short-circuits when the
        refund has already left APPROVED.
        """
        if refund.status == RefundStatus.EXECUTING.value:
            # Already executed — likely a webhook retry. Return the
            # current row without re-firing the outbound Payment.
            return refund
        if refund.status != RefundStatus.APPROVED.value:
            raise ValueError(f"Refund {refund.reference}: cannot :execute from {refund.status!r}")
        if not _actor_has_perm(actor, PERM_EXECUTE):
            raise PermissionError(f"actor {actor!r} missing {PERM_EXECUTE!r} permission")
        # High-risk org policy: executor must differ from approver unless
        # the actor carries `payments.refund.self_approve`. Service-layer
        # only — the DB doesn't enforce executor distinction.
        if (
            actor is not None
            and refund.approved_by_id is not None
            and getattr(actor, "pk", None) == refund.approved_by_id
            and not _actor_has_perm(actor, PERM_SELF_APPROVE)
        ):
            raise PermissionError(
                f"Approver cannot also execute a refund without {PERM_SELF_APPROVE!r}",
            )

        refund.executed_by = actor
        refund.executed_at = timezone.now()
        refund.save(update_fields=["executed_by", "executed_at", "updated_at"])

        # Mint the gateway-bound Payment row. The Refund FK lives on
        # `Payment.meta`; the reverse direction is `Refund.against_payment`
        # which points to the original *inbound* payment, not the outbound
        # refund payment. Guard against duplicates from concurrent
        # execute attempts that raced past the status check above.
        outbound_exists = Payment.objects.filter(
            booking=refund.booking,
            purpose=PaymentPurpose.REFUND.value,
            meta__refund_id=refund.pk,
        ).exists()
        if not outbound_exists:
            Payment.objects.create(
                booking=refund.booking,
                purpose=PaymentPurpose.REFUND.value,
                status=PaymentStatus.PROCESSING.value,
                amount=refund.amount,
                currency=refund.currency,
                meta={"refund_id": refund.pk},
            )

        # TODO: queue Celery `process_refund(refund.id)` — for now we just
        # record the EXECUTING state and rely on the webhook pipeline (or a
        # manual transition) to advance it to SUCCEEDED / FAILED.
        return refund._transition(RefundStatus.EXECUTING.value, actor=actor)

    # ------------------------------------------------------------------
    # Convenience constructor: cancellation → refund
    # ------------------------------------------------------------------
    @classmethod
    @transaction.atomic
    def from_cancellation(
        cls,
        booking: Any,
        *,
        reason: str,
        requested_by: Any,
    ) -> Refund | None:
        """Open a `Refund` sized as `paid_total - cancellation_fee`.

        Returns `None` when the fee fully consumes paid money. Security-
        deposit money is *not* rolled in — the SD workflow runs its own
        release/refund track independently.
        """
        paid_total = Payment.objects.filter(
            booking=booking,
            status=PaymentStatus.SUCCEEDED.value,
            purpose__in=(
                PaymentPurpose.DEPOSIT.value,
                PaymentPurpose.BALANCE.value,
            ),
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
        if paid_total <= 0:
            return None

        finance = booking.property.finance
        policy = finance.effective_cancellation_policy()
        fee_amount = Decimal(str(policy.get("fee_amount") or 0))
        fee_percent = Decimal(str(policy.get("fee_percent") or 0))
        percent_component = (
            (paid_total * fee_percent / Decimal(100)) if fee_percent > 0 else Decimal("0")
        )
        fee = max(fee_amount, percent_component).quantize(Decimal("0.01"))

        refundable = (paid_total - fee).quantize(Decimal("0.01"))
        if refundable <= 0:
            return None

        return cls.request(
            booking=booking,
            amount=refundable,
            currency=booking.currency,
            purpose_track=RefundPurposeTrack.BALANCE.value,
            reason_code=RefundReasonCode.CANCELLATION.value,
            reason_notes=reason,
            requested_by=requested_by,
        )
