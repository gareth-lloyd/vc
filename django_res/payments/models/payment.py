"""`Payment` — the unified money-movement ledger row.

One row per attempted charge/refund/etc. The lifecycle is on `status`; the
purpose enum partitions DEPOSIT/BALANCE/SECURITY_DEPOSIT/CONCIERGE/REFUND/
ADJUSTMENT rows under a single table.

Transitions live as methods on the model — `waive`, `mark_paid`, and the
generic `transition_to`. Each one wraps state mutation + PaymentEvent +
signal dispatch in `transaction.atomic` so external observers never see
half-applied transitions.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.db import models, transaction
from django.db.models import Q

from core.models.base import AuditedModel
from core.refs import generate_reference
from payments import signals as payment_signals
from payments.enums import (
    ACTIVE_PAYMENT_STATUSES,
    EventSource,
    PaymentMethod,
    PaymentProvider,
    PaymentPurpose,
    PaymentStatus,
)

if TYPE_CHECKING:
    from payments.models.payment_event import PaymentEvent
    from payments.models.webhook_delivery import WebhookDelivery


class Payment(AuditedModel):
    """A single ledger row tracking one money-movement attempt."""

    reference = models.CharField(max_length=32, unique=True)
    booking = models.ForeignKey(
        "reservations.Booking",
        on_delete=models.PROTECT,
        related_name="payments",
    )
    purpose = models.CharField(max_length=24, choices=PaymentPurpose.choices)
    status = models.CharField(
        max_length=16,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.ForeignKey(
        "pricing.Currency",
        on_delete=models.PROTECT,
        related_name="+",
    )
    provider = models.CharField(
        max_length=32,
        choices=PaymentProvider.choices,
        blank=True,
    )
    provider_reference = models.CharField(max_length=128, blank=True)
    payment_method = models.CharField(
        max_length=16,
        choices=PaymentMethod.choices,
        blank=True,
    )
    token = models.CharField(max_length=128, blank=True)
    signature = models.CharField(max_length=256, blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    requested_at = models.DateTimeField(null=True, blank=True)
    settled_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True)
    meta = models.JSONField(default=dict, blank=True)
    concierge_item = models.ForeignKey(
        "reservations.BookingConciergeItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
    )

    class Meta:
        indexes = [
            models.Index(fields=["booking", "purpose"]),
            models.Index(fields=["status", "due_at"]),
            models.Index(fields=["provider_reference"]),
        ]
        permissions = [
            ("waive_payment", "Can waive a scheduled payment"),
            ("mark_paid_payment", "Can mark a payment as manually paid"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["booking", "purpose"],
                condition=(
                    Q(status__in=ACTIVE_PAYMENT_STATUSES)
                    & Q(
                        purpose__in=[
                            PaymentPurpose.DEPOSIT.value,
                            PaymentPurpose.BALANCE.value,
                        ]
                    )
                ),
                name="unique_active_payment_per_purpose",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.reference} ({self.purpose}/{self.status})"

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------
    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.reference:
            self.reference = generate_reference("P", model=type(self))
        super().save(*args, **kwargs)

    # ------------------------------------------------------------------
    # Transitions
    # ------------------------------------------------------------------
    @transaction.atomic
    def transition_to(
        self,
        new_status: str,
        *,
        source: str = EventSource.USER.value,
        actor: Any = None,
        delivery: WebhookDelivery | None = None,
        reason: str = "",
        kind: str = "",
        **meta: Any,
    ) -> Payment:
        """Generic status transition. Writes a `PaymentEvent` and dispatches
        the appropriate signal when the new status is terminal.
        """
        from payments.models.payment_event import PaymentEvent

        old_status = self.status
        self.status = new_status
        if reason:
            self.failure_reason = reason
        update_fields = ["status", "failure_reason", "updated_at"]
        if new_status == PaymentStatus.SUCCEEDED.value and self.settled_at is None:
            from django.utils import timezone

            self.settled_at = timezone.now()
            update_fields.append("settled_at")
        self.save(update_fields=update_fields)

        PaymentEvent.objects.create(
            payment=self,
            from_status=old_status,
            to_status=new_status,
            kind=kind,
            source=source,
            actor=actor,
            delivery=delivery,
            meta=meta or {},
        )

        self._dispatch_terminal_signal(new_status)
        return self

    def _dispatch_terminal_signal(self, new_status: str) -> None:
        if new_status == PaymentStatus.SUCCEEDED.value:
            if self.purpose == PaymentPurpose.REFUND.value:
                payment_signals.payment_refunded.send(sender=type(self), payment=self)
            else:
                payment_signals.payment_succeeded.send(sender=type(self), payment=self)
        elif new_status == PaymentStatus.FAILED.value:
            payment_signals.payment_failed.send(sender=type(self), payment=self)
        elif new_status == PaymentStatus.REFUNDED.value:
            payment_signals.payment_refunded.send(sender=type(self), payment=self)
        elif new_status == PaymentStatus.WAIVED.value:
            payment_signals.payment_waived.send(sender=type(self), payment=self)

    @transaction.atomic
    def waive(self, reason: str, *, actor: Any = None) -> Payment:
        """Operator-applied transition: PENDING/PROCESSING → WAIVED.

        Sets `failure_reason="WAIVED:<reason>"`, writes a PaymentEvent and
        fires the `payment_waived` signal so reservations advances the booking
        as if the payment had succeeded.
        """
        if self.status not in (
            PaymentStatus.PENDING.value,
            PaymentStatus.PROCESSING.value,
        ):
            raise ValueError(f"Cannot waive Payment {self.reference} from status {self.status!r}")
        return self.transition_to(
            PaymentStatus.WAIVED.value,
            source=EventSource.USER.value,
            actor=actor,
            reason=f"WAIVED:{reason}",
            kind="WAIVED",
            reason_note=reason,
        )

    @transaction.atomic
    def mark_paid(
        self,
        amount: Decimal,
        paid_at: datetime,
        method: str,
        reference: str,
        notes: str = "",
        *,
        actor: Any = None,
    ) -> Payment:
        """Operator-applied transition: PENDING → SUCCEEDED.

        Records a manual bank-transfer / cash receipt. Sets `provider`,
        `provider_reference`, `settled_at`, then transitions to SUCCEEDED via
        the generic `transition_to` so the `payment_succeeded` signal fires
        through the usual path.
        """
        if self.status != PaymentStatus.PENDING.value:
            raise ValueError(
                f"Cannot mark_paid on Payment {self.reference} from status {self.status!r}"
            )
        # The operator is the system-of-record — set provider per the spec.
        # Bank transfer → MANUAL_BANK_TRANSFER; everything else → OTHER.
        if method == PaymentMethod.BANK_TRANSFER.value:
            self.provider = PaymentProvider.MANUAL_BANK_TRANSFER.value
        else:
            self.provider = PaymentProvider.OTHER.value
        self.payment_method = method
        self.provider_reference = reference
        self.amount = amount
        self.settled_at = paid_at
        self.signature = ""
        self.save(
            update_fields=[
                "provider",
                "payment_method",
                "provider_reference",
                "amount",
                "settled_at",
                "signature",
                "updated_at",
            ]
        )
        return self.transition_to(
            PaymentStatus.SUCCEEDED.value,
            source=EventSource.USER.value,
            actor=actor,
            kind="MARK_PAID",
            notes=notes,
        )

    # ------------------------------------------------------------------
    # Conveniences for the audit/event tail.
    # ------------------------------------------------------------------
    def events(self) -> models.QuerySet[PaymentEvent]:
        return self.payment_events.all()
