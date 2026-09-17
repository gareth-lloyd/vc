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

from core.exceptions import DomainValidationError, InvalidSecurityDepositKind
from core.locking import refresh_locked
from core.models.base import AuditedModel
from core.refs import reference_db_default
from core.transitions import assert_allowed, transition
from payments import signals as payment_signals
from payments.enums import (
    SD_ALLOWED_TRANSITIONS,
    TERMINAL_SD_STATUSES,
    EventSource,
    SecurityDepositKind,
    SecurityDepositStatus,
)

if TYPE_CHECKING:
    from payments.models.payment_event import PaymentEvent
    from reservations.models import DamageClaim


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
    # The structured claim that justifies a capture / partial refund (BUG-008).
    # SET_NULL: a claim may be hard-deleted without dragging the SD's money
    # history down with it, but the SD keeps its captured_amount audit.
    damage_claim = models.ForeignKey(
        "reservations.DamageClaim",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="security_deposits",
    )
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

    def assert_capturable_amount(self, captured_amount: Decimal) -> None:
        """A claim captures between zero and the full held amount."""
        if captured_amount < 0:
            message = f"captured_amount {captured_amount} is negative"
        elif captured_amount > self.amount:
            message = f"captured_amount {captured_amount} exceeds amount {self.amount}"
        else:
            return
        raise DomainValidationError(
            f"SD {self.reference}: {message}",
            field_errors={"captured_amount": [message]},
        )

    def _assert_kind(self, kind: str, action: str) -> None:
        if self.kind != kind:
            raise InvalidSecurityDepositKind(f"SD {self.reference}: {action} only valid for {kind}")

    # ------------------------------------------------------------------
    # Transitions
    #
    # Edges live in `SD_ALLOWED_TRANSITIONS`; `_transition` moves through
    # `core.transitions` (lock → guard → save → PaymentEvent). Wrappers that
    # branch on kind or check amounts lock first, then refuse in a fixed
    # order — wrong kind (409 `invalid_sd_kind`), illegal status (409
    # `invalid_transition`), bad amount (400) — and compute field writes from
    # the locked row so they land in the same UPDATE as the status.
    # ------------------------------------------------------------------
    def _transition(
        self,
        new_status: str,
        *,
        source: str = EventSource.USER.value,
        actor: Any = None,
        kind: str = "",
        extra_updates: dict[str, Any] | None = None,
        **meta: Any,
    ) -> SecurityDeposit:
        from payments.models.payment_event import PaymentEvent

        def record(from_status: str, to_status: str) -> None:
            PaymentEvent.objects.create(
                security_deposit=self,
                from_status=from_status,
                to_status=to_status,
                kind=kind,
                source=source,
                actor=actor,
                meta=meta or {},
            )

        transition(
            self,
            new_status,
            table=SD_ALLOWED_TRANSITIONS,
            extra_updates=extra_updates,
            record=record,
        )
        return self

    def transition_to_pre_authed(self, *, actor: Any = None, **meta: Any) -> SecurityDeposit:
        return self._transition(
            SecurityDepositStatus.PRE_AUTHED.value,
            actor=actor,
            kind="HOLD",
            **meta,
        )

    @transaction.atomic
    def transition_to_released(self, *, actor: Any = None, **meta: Any) -> SecurityDeposit:
        refresh_locked(self)
        extra_updates: dict[str, Any] = {"released_at": timezone.now()}
        if self.kind == SecurityDepositKind.PRE_AUTH_HOLD.value:
            target = SecurityDepositStatus.RELEASED.value
        else:
            target = SecurityDepositStatus.REFUNDED.value
            extra_updates["refunded_amount"] = self.amount
        sd = self._transition(
            target, actor=actor, kind="RELEASE", extra_updates=extra_updates, **meta
        )
        payment_signals.security_deposit_released.send(sender=type(self), sd=sd)
        return sd

    @transaction.atomic
    def transition_to_captured(
        self,
        *,
        captured_amount: Decimal,
        damage_claim: DamageClaim | None,
        actor: Any = None,
        **meta: Any,
    ) -> SecurityDeposit:
        refresh_locked(self)
        self._assert_kind(SecurityDepositKind.PRE_AUTH_HOLD.value, ":claim → CAPTURED")
        target = SecurityDepositStatus.CAPTURED.value
        assert_allowed(self, target, table=SD_ALLOWED_TRANSITIONS)
        self.assert_capturable_amount(captured_amount)
        return self._transition(
            target,
            actor=actor,
            kind="CLAIM",
            extra_updates={"captured_amount": captured_amount, "damage_claim": damage_claim},
            **meta,
        )

    @transaction.atomic
    def transition_to_partially_refunded(
        self,
        *,
        captured_amount: Decimal,
        damage_claim: DamageClaim | None,
        actor: Any = None,
        **meta: Any,
    ) -> SecurityDeposit:
        refresh_locked(self)
        self._assert_kind(SecurityDepositKind.BT_REFUNDABLE.value, "PARTIALLY_REFUNDED")
        target = SecurityDepositStatus.PARTIALLY_REFUNDED.value
        assert_allowed(self, target, table=SD_ALLOWED_TRANSITIONS)
        # Bounds matter doubly here: `refunded_amount = amount - captured`,
        # so an over-amount capture silently produced a negative refund.
        self.assert_capturable_amount(captured_amount)
        sd = self._transition(
            target,
            actor=actor,
            kind="CLAIM",
            extra_updates={
                "captured_amount": captured_amount,
                "refunded_amount": self.amount - captured_amount,
                "damage_claim": damage_claim,
                "released_at": timezone.now(),
            },
            **meta,
        )
        payment_signals.security_deposit_released.send(sender=type(self), sd=sd)
        return sd

    @transaction.atomic
    def transition_to_held(self, *, actor: Any = None, **meta: Any) -> SecurityDeposit:
        refresh_locked(self)
        self._assert_kind(SecurityDepositKind.BT_REFUNDABLE.value, "HELD")
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
            target = SecurityDepositStatus.EXPIRED.value
        else:
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

    def transition_to_failed(
        self,
        *,
        reason: str,
        actor: Any = None,
        **meta: Any,
    ) -> SecurityDeposit:
        return self._transition(
            SecurityDepositStatus.FAILED.value,
            source=EventSource.SYSTEM.value,
            actor=actor,
            kind="FAILED",
            extra_updates={"failure_reason": reason},
            reason=reason,
            **meta,
        )

    def events(self) -> models.QuerySet[PaymentEvent]:
        return self.security_deposit_events.all()
