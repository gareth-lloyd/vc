"""`SecurityDeposit` — first-class workflow object for the SD lifecycle.

Mirrors `Refund` in shape: the workflow row owns the state machine; the
gateway-transaction audit lives on spawned `Payment(purpose=SECURITY_DEPOSIT)`
rows linked back via `meta['security_deposit_id']`.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone

from core.locking import refresh_locked
from core.models.base import AuditedModel
from core.refs import reference_db_default
from payments import signals as payment_signals
from payments.enums import (
    TERMINAL_SD_STATUSES,
    EventSource,
    SecurityDepositKind,
    SecurityDepositStatus,
)

if TYPE_CHECKING:
    from payments.models.payment_event import PaymentEvent


class SecurityDeposit(AuditedModel):
    """One security-deposit workflow per booking-attempt."""

    reference = models.CharField(
        max_length=32,
        unique=True,
        db_default=reference_db_default("SD", sequence="security_deposit_reference_seq"),
    )
    booking = models.ForeignKey(
        "reservations.Booking",
        on_delete=models.PROTECT,
        related_name="security_deposits",
    )
    kind = models.CharField(max_length=24, choices=SecurityDepositKind.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.ForeignKey(
        "pricing.Currency",
        on_delete=models.PROTECT,
        related_name="+",
    )
    status = models.CharField(
        max_length=24,
        choices=SecurityDepositStatus.choices,
    )
    due_at = models.DateTimeField(null=True, blank=True)
    hold_expires_at = models.DateTimeField(null=True, blank=True)
    release_after_departure_days = models.PositiveSmallIntegerField(null=True, blank=True)
    release_scheduled_for = models.DateField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)
    captured_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    refunded_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    # `DamageClaim` lives in `reservations/` per 05-reservations.md but is not
    # yet implemented by the parallel agent. Track the link as a plain PK
    # column for now; flip back to a FK once the model lands.
    # TODO: convert `damage_claim_id` to FK("reservations.DamageClaim", on_delete=SET_NULL)
    damage_claim_id = models.PositiveBigIntegerField(null=True, blank=True)
    requested_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="security_deposits_requested",
    )
    requested_at = models.DateTimeField(default=timezone.now)
    failure_reason = models.CharField(max_length=255, blank=True)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["booking", "status"]),
            models.Index(fields=["status", "release_scheduled_for"]),
            models.Index(fields=["status", "hold_expires_at"]),
        ]
        permissions = [
            ("release_securitydeposit", "Can release a security deposit"),
            ("claim_securitydeposit", "Can claim against a security deposit"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="securitydeposit_amount_positive",
            ),
            models.UniqueConstraint(
                fields=["booking"],
                condition=~Q(status__in=list(TERMINAL_SD_STATUSES)),
                name="one_active_security_deposit_per_booking",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.reference} ({self.kind}/{self.status})"

    def _assert_capturable_amount(self, captured_amount: Decimal) -> None:
        """A claim captures between zero and the full held amount."""
        if captured_amount < 0:
            raise ValueError(f"SD {self.reference}: captured_amount {captured_amount} is negative")
        if captured_amount > self.amount:
            raise ValueError(
                f"SD {self.reference}: captured_amount {captured_amount} "
                f"exceeds amount {self.amount}"
            )

    # ------------------------------------------------------------------
    # Transitions
    #
    # Each public `transition_to_*` is atomic and re-reads the row under
    # lock (`refresh_locked`) before its status guard, so a stale instance
    # (operator double-click, concurrent capture vs. release) loses with a
    # ValueError instead of double-firing — and its field writes roll back
    # with the failed transition rather than persisting on their own.
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
    ) -> SecurityDeposit:
        from payments.models.payment_event import PaymentEvent

        old_status = self.status
        self.status = new_status
        self.save(update_fields=["status", "updated_at"])
        PaymentEvent.objects.create(
            security_deposit=self,
            from_status=old_status,
            to_status=new_status,
            kind=kind,
            source=source,
            actor=actor,
            meta=meta or {},
        )
        return self

    @transaction.atomic
    def transition_to_pre_authed(self, *, actor: Any = None, **meta: Any) -> SecurityDeposit:
        refresh_locked(self)
        if self.status != SecurityDepositStatus.AWAITING_DETAILS.value:
            raise ValueError(f"SD {self.reference}: cannot :hold from status {self.status!r}")
        return self._transition(
            SecurityDepositStatus.PRE_AUTHED.value,
            actor=actor,
            kind="HOLD",
            **meta,
        )

    @transaction.atomic
    def transition_to_released(self, *, actor: Any = None, **meta: Any) -> SecurityDeposit:
        refresh_locked(self)
        if self.kind == SecurityDepositKind.PRE_AUTH_HOLD.value:
            if self.status != SecurityDepositStatus.PRE_AUTHED.value:
                raise ValueError(
                    f"SD {self.reference}: cannot :release from status {self.status!r}"
                )
            target = SecurityDepositStatus.RELEASED.value
        else:
            if self.status != SecurityDepositStatus.HELD.value:
                raise ValueError(
                    f"SD {self.reference}: cannot :release from status {self.status!r}"
                )
            target = SecurityDepositStatus.REFUNDED.value
        self.released_at = timezone.now()
        if self.kind == SecurityDepositKind.BT_REFUNDABLE.value:
            self.refunded_amount = self.amount
        self.save(update_fields=["released_at", "refunded_amount", "updated_at"])
        sd = self._transition(target, actor=actor, kind="RELEASE", **meta)
        payment_signals.security_deposit_released.send(sender=type(self), sd=sd)
        return sd

    @transaction.atomic
    def transition_to_captured(
        self,
        *,
        captured_amount: Decimal,
        damage_claim: Any,
        actor: Any = None,
        **meta: Any,
    ) -> SecurityDeposit:
        refresh_locked(self)
        if self.kind != SecurityDepositKind.PRE_AUTH_HOLD.value:
            raise ValueError(f"SD {self.reference}: :claim → CAPTURED only valid for PRE_AUTH_HOLD")
        if self.status != SecurityDepositStatus.PRE_AUTHED.value:
            raise ValueError(f"SD {self.reference}: cannot :claim from status {self.status!r}")
        self._assert_capturable_amount(captured_amount)
        self.captured_amount = captured_amount
        self.damage_claim_id = getattr(damage_claim, "pk", damage_claim)
        self.save(update_fields=["captured_amount", "damage_claim_id", "updated_at"])
        return self._transition(
            SecurityDepositStatus.CAPTURED.value,
            actor=actor,
            kind="CLAIM",
            **meta,
        )

    @transaction.atomic
    def transition_to_partially_refunded(
        self,
        *,
        captured_amount: Decimal,
        damage_claim: Any,
        actor: Any = None,
        **meta: Any,
    ) -> SecurityDeposit:
        refresh_locked(self)
        if self.kind != SecurityDepositKind.BT_REFUNDABLE.value:
            raise ValueError(
                f"SD {self.reference}: PARTIALLY_REFUNDED only valid for BT_REFUNDABLE"
            )
        if self.status != SecurityDepositStatus.HELD.value:
            raise ValueError(
                f"SD {self.reference}: cannot partial-refund from status {self.status!r}"
            )
        # Bounds matter doubly here: `refunded_amount = amount - captured`,
        # so an over-amount capture silently produced a negative refund.
        self._assert_capturable_amount(captured_amount)
        self.captured_amount = captured_amount
        self.refunded_amount = self.amount - captured_amount
        self.damage_claim_id = getattr(damage_claim, "pk", damage_claim)
        self.released_at = timezone.now()
        self.save(
            update_fields=[
                "captured_amount",
                "refunded_amount",
                "damage_claim_id",
                "released_at",
                "updated_at",
            ]
        )
        sd = self._transition(
            SecurityDepositStatus.PARTIALLY_REFUNDED.value,
            actor=actor,
            kind="CLAIM",
            **meta,
        )
        payment_signals.security_deposit_released.send(sender=type(self), sd=sd)
        return sd

    @transaction.atomic
    def transition_to_held(self, *, actor: Any = None, **meta: Any) -> SecurityDeposit:
        refresh_locked(self)
        if self.kind != SecurityDepositKind.BT_REFUNDABLE.value:
            raise ValueError(f"SD {self.reference}: HELD only valid for BT_REFUNDABLE")
        if self.status != SecurityDepositStatus.AWAITING_BT.value:
            raise ValueError(f"SD {self.reference}: cannot transition to HELD from {self.status!r}")
        return self._transition(
            SecurityDepositStatus.HELD.value,
            actor=actor,
            kind="MARK_PAID",
            **meta,
        )

    @transaction.atomic
    def transition_to_expired(self, *, actor: Any = None, **meta: Any) -> SecurityDeposit:
        refresh_locked(self)
        if self.kind == SecurityDepositKind.PRE_AUTH_HOLD.value:
            if self.status != SecurityDepositStatus.PRE_AUTHED.value:
                raise ValueError(f"SD {self.reference}: cannot expire from status {self.status!r}")
            target = SecurityDepositStatus.EXPIRED.value
        else:
            if self.status != SecurityDepositStatus.AWAITING_BT.value:
                raise ValueError(f"SD {self.reference}: cannot fail from status {self.status!r}")
            target = SecurityDepositStatus.FAILED.value
        sd = self._transition(
            target,
            source=EventSource.SYSTEM.value,
            actor=actor,
            kind="EXPIRED",
            **meta,
        )
        payment_signals.security_deposit_expired.send(sender=type(self), sd=sd)
        return sd

    @transaction.atomic
    def transition_to_failed(
        self,
        *,
        reason: str,
        actor: Any = None,
        **meta: Any,
    ) -> SecurityDeposit:
        refresh_locked(self)
        if self.status not in (
            SecurityDepositStatus.AWAITING_DETAILS.value,
            SecurityDepositStatus.PRE_AUTHED.value,
            SecurityDepositStatus.AWAITING_BT.value,
        ):
            raise ValueError(f"SD {self.reference}: cannot fail from status {self.status!r}")
        self.failure_reason = reason
        self.save(update_fields=["failure_reason", "updated_at"])
        return self._transition(
            SecurityDepositStatus.FAILED.value,
            source=EventSource.SYSTEM.value,
            actor=actor,
            kind="FAILED",
            reason=reason,
            **meta,
        )

    def events(self) -> models.QuerySet[PaymentEvent]:
        return self.security_deposit_events.all()
