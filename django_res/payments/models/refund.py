"""`Refund` — first-class workflow object for money returning to the guest.

Separation-of-duties is the point: the `requested_by` user cannot be the
same as `approved_by` (DB CheckConstraint). The Refund itself never talks
to the gateway — `:execute` creates a `Payment(purpose=REFUND,
status=PROCESSING)` that rides on the normal payment-webhook pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db import models, transaction
from django.db.models import F, Q
from django.utils import timezone

from core.models.base import AuditedModel
from core.refs import reference_db_default
from payments.enums import (
    EventSource,
    RefundMethod,
    RefundPurposeTrack,
    RefundReasonCode,
    RefundStatus,
)

if TYPE_CHECKING:
    from payments.models.payment_event import PaymentEvent


class Refund(AuditedModel):
    """One refund-request workflow row."""

    reference = models.CharField(
        max_length=32,
        unique=True,
        db_default=reference_db_default("R", sequence="refund_reference_seq"),
    )
    booking = models.ForeignKey(
        "reservations.Booking",
        on_delete=models.PROTECT,
        related_name="refunds",
    )
    against_payment = models.ForeignKey(
        "payments.Payment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="refunds_against",
    )
    purpose_track = models.CharField(
        max_length=24,
        choices=RefundPurposeTrack.choices,
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.ForeignKey(
        "pricing.Currency",
        on_delete=models.PROTECT,
        related_name="+",
    )
    status = models.CharField(
        max_length=16,
        choices=RefundStatus.choices,
        default=RefundStatus.PENDING,
    )
    reason_code = models.CharField(
        max_length=32,
        choices=RefundReasonCode.choices,
    )
    reason_notes = models.TextField(blank=True)
    method = models.CharField(
        max_length=24,
        choices=RefundMethod.choices,
        default=RefundMethod.ONLINE_GATEWAY,
    )
    requested_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="refunds_requested",
    )
    requested_at = models.DateTimeField(default=timezone.now)
    approved_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="refunds_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="refunds_rejected",
    )
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    executed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="refunds_executed",
    )
    executed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    settled_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True)
    meta = models.JSONField(default=dict, blank=True)
    security_deposit = models.ForeignKey(
        "payments.SecurityDeposit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="refunds",
    )

    class Meta:
        indexes = [
            models.Index(fields=["booking", "status"]),
            models.Index(fields=["status", "requested_at"]),
            models.Index(fields=["against_payment"]),
        ]
        permissions = [
            ("approve_refund", "Can approve a refund"),
            ("execute_refund", "Can execute a refund"),
            ("self_approve_refund", "Can self-approve or self-execute a refund"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="refund_amount_positive",
            ),
            # Separation of duties: requester cannot self-approve (DB floor,
            # no permission escape hatch — `RefundService.approve` mirrors
            # this unconditionally). `payments.self_approve_refund` relaxes
            # only the approver/executor split in `RefundService.execute`,
            # which this constraint deliberately doesn't cover.
            models.CheckConstraint(
                condition=Q(approved_by__isnull=True) | ~Q(approved_by=F("requested_by")),
                name="refund_separation_of_duties",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.reference} ({self.status})"

    # ------------------------------------------------------------------
    # Transitions
    # ------------------------------------------------------------------
    @transaction.atomic
    def _transition(
        self,
        new_status: str,
        *,
        source: str = EventSource.USER.value,
        actor: Any = None,
        kind: str = "",
        **meta: Any,
    ) -> Refund:
        from core.exceptions import InvalidTransition
        from core.locking import refresh_locked
        from payments.enums import REFUND_ALLOWED_TRANSITIONS
        from payments.models.payment_event import PaymentEvent

        # Table-driven floor (mirrors `Payment.transition_to`): the service
        # layers policy on top, but no caller can skip a workflow stage or
        # transition a stale row.
        refresh_locked(self)
        allowed = REFUND_ALLOWED_TRANSITIONS.get(self.status, frozenset())
        if new_status not in allowed:
            raise InvalidTransition(self.status, new_status, allowed=sorted(allowed))

        old_status = self.status
        self.status = new_status
        self.save(update_fields=["status", "updated_at"])
        PaymentEvent.objects.create(
            refund=self,
            from_status=old_status,
            to_status=new_status,
            kind=kind,
            source=source,
            actor=actor,
            meta=meta or {},
        )
        return self

    def events(self) -> models.QuerySet[PaymentEvent]:
        return self.refund_events.all()
