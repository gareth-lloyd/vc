"""`PaymentEvent` — append-only audit row, polymorphic over Payment / Refund /
SecurityDeposit.

Exactly one of (`payment`, `refund`, `security_deposit`) is set per row;
the `CheckConstraint` enforces this in the DB so audit rows can never
straddle two workflows.
"""

from __future__ import annotations

from django.db import models
from django.db.models import Q

from core.models.base import TimestampedModel
from payments.enums import EventSource


class PaymentEvent(TimestampedModel):
    """One state-transition or audit-event row.

    `from_status` / `to_status` are stored as opaque strings so a single
    table can carry transitions from all three workflows (Payment, Refund,
    SecurityDeposit) without coupling to any one enum.
    """

    payment = models.ForeignKey(
        "payments.Payment",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="payment_events",
    )
    refund = models.ForeignKey(
        "payments.Refund",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="refund_events",
    )
    security_deposit = models.ForeignKey(
        "payments.SecurityDeposit",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="security_deposit_events",
    )
    from_status = models.CharField(max_length=32, blank=True)
    to_status = models.CharField(max_length=32, blank=True)
    kind = models.CharField(max_length=32, blank=True)
    source = models.CharField(
        max_length=16,
        choices=EventSource.choices,
        default=EventSource.SYSTEM,
    )
    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    delivery = models.ForeignKey(
        "payments.WebhookDelivery",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )
    payload_hash = models.CharField(max_length=128, blank=True)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["payment", "created_at"]),
            models.Index(fields=["refund", "created_at"]),
            models.Index(fields=["security_deposit", "created_at"]),
        ]
        constraints = [
            # Exactly one of the three FKs must be non-null.
            models.CheckConstraint(
                condition=(
                    (
                        Q(payment__isnull=False)
                        & Q(refund__isnull=True)
                        & Q(security_deposit__isnull=True)
                    )
                    | (
                        Q(payment__isnull=True)
                        & Q(refund__isnull=False)
                        & Q(security_deposit__isnull=True)
                    )
                    | (
                        Q(payment__isnull=True)
                        & Q(refund__isnull=True)
                        & Q(security_deposit__isnull=False)
                    )
                ),
                name="paymentevent_exactly_one_target",
            ),
        ]

    def __str__(self) -> str:
        target = self.payment_id or self.refund_id or self.security_deposit_id
        return f"PaymentEvent({target}: {self.from_status} → {self.to_status})"
