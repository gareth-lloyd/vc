"""DamageClaim service — the sanctioned write path for damages claims.

`DamageClaimService` owns the claim's small set of invariants: the currency is
pinned to the booking's (a claim funds an SD capture, which is single-currency),
the amount is strictly positive (surfaced as a 400 rather than the DB check
constraint's 500), and the `created_by`/`updated_by` actor is stamped. The
AuditLog trail rides the model's `track()` registration (BUG-008), so `.save()`
/ `.delete()` here are audited without extra plumbing.

Lifecycle is the `DamageClaimStatus` enum, enforced as a small state machine:
`OPEN → APPROVED → SETTLED`, with `WITHDRAWN` reachable from either live state.
`approve()` is the operator sign-off; `settle()` is the side effect of the
security-deposit capture linking the claim (wired from
`payments.SecurityDepositService.claim`); `withdraw()` is the operator "cancel".
SETTLED/WITHDRAWN are terminal (no further transitions, no edits). A true
mistake can still be hard-deleted (the SD FK is SET_NULL, so the deposit's
money trail survives).
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.db import transaction

from core.exceptions import DomainValidationError, InvalidTransition
from core.locking import refresh_locked
from reservations.enums import DamageClaimStatus
from reservations.models import DamageClaim

_OPEN = DamageClaimStatus.OPEN.value
_APPROVED = DamageClaimStatus.APPROVED.value
_SETTLED = DamageClaimStatus.SETTLED.value
_WITHDRAWN = DamageClaimStatus.WITHDRAWN.value

#: Allowed status transitions. SETTLED/WITHDRAWN are terminal (empty sets).
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    _OPEN: {_APPROVED, _SETTLED, _WITHDRAWN},
    _APPROVED: {_SETTLED, _WITHDRAWN},
    _SETTLED: set(),
    _WITHDRAWN: set(),
}

#: Closed records — no further edits. Derived from the terminal (empty) rows of
#: the transition table so the two can't drift.
_CLOSED_STATES = frozenset(s for s, allowed in _ALLOWED_TRANSITIONS.items() if not allowed)

if TYPE_CHECKING:
    from pricing.models import Currency
    from reservations.models import Booking


class DamageClaimService:
    """Create / update / withdraw / delete damages claims, with the invariants."""

    @classmethod
    @transaction.atomic
    def create(
        cls,
        booking: Booking,
        *,
        amount: Decimal,
        description: str,
        currency: Currency | None = None,
        itemized_lines: list[dict[str, Any]] | None = None,
        actor: Any = None,
    ) -> DamageClaim:
        currency = cls._resolve_currency(booking, currency)
        cls._validate_amount(amount)
        return DamageClaim.objects.create(
            booking=booking,
            currency=currency,
            amount=amount,
            description=description,
            itemized_lines=itemized_lines if itemized_lines is not None else [],
            created_by=actor,
            updated_by=actor,
        )

    @classmethod
    @transaction.atomic
    def update(
        cls,
        claim: DamageClaim,
        *,
        actor: Any = None,
        **fields: Any,
    ) -> DamageClaim:
        # Lock + reload before the closed-state guard so a concurrent
        # settle/withdraw can't slip past it and then be clobbered by the
        # full-row save below (same race `_transition` closes).
        refresh_locked(claim)
        if claim.status in _CLOSED_STATES:
            raise DomainValidationError(
                message="A settled or withdrawn claim cannot be edited.",
            )
        if "currency" in fields:
            fields["currency"] = cls._resolve_currency(claim.booking, fields["currency"])
        if "amount" in fields:
            cls._validate_amount(fields["amount"])
        for name, value in fields.items():
            setattr(claim, name, value)
        claim.updated_by = actor
        claim.save()
        return claim

    @classmethod
    @transaction.atomic
    def approve(cls, claim: DamageClaim, *, actor: Any = None) -> DamageClaim:
        """Operator sign-off: OPEN → APPROVED."""
        return cls._transition(claim, _APPROVED, actor=actor)

    @classmethod
    @transaction.atomic
    def settle(cls, claim: DamageClaim, *, actor: Any = None) -> DamageClaim:
        """Settle the claim (OPEN/APPROVED → SETTLED).

        Driven by the SD capture linking the claim, not a separate operator
        click — settlement is the money-move's side effect.
        """
        return cls._transition(claim, _SETTLED, actor=actor)

    @classmethod
    @transaction.atomic
    def withdraw(cls, claim: DamageClaim, *, actor: Any = None) -> DamageClaim:
        """Operator cancel: OPEN/APPROVED → WITHDRAWN."""
        return cls._transition(claim, _WITHDRAWN, actor=actor)

    @classmethod
    @transaction.atomic
    def delete(cls, claim: DamageClaim, *, actor: Any = None) -> None:
        claim.delete()

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------
    @staticmethod
    def _transition(claim: DamageClaim, to_status: str, *, actor: Any = None) -> DamageClaim:
        """Lock + reload the row, guard the transition, stamp + save in place.

        `refresh_locked` (the shared `core.locking` helper, as in
        `Refund._transition`) takes `SELECT … FOR UPDATE` and reloads `claim`
        before the guard, closing the read-modify-write race between two
        concurrent transitions (e.g. an operator withdraw racing an SD-capture
        settle). Mutating the caller's own instance keeps `updated_at` fresh for
        a view that serialises the response without a refetch.
        """
        refresh_locked(claim)
        allowed = _ALLOWED_TRANSITIONS[claim.status]
        if to_status not in allowed:
            raise InvalidTransition(claim.status, to_status, allowed=sorted(allowed))
        claim.status = to_status
        claim.updated_by = actor
        claim.save(update_fields=["status", "updated_by", "updated_at"])
        return claim

    # ------------------------------------------------------------------
    # Invariants
    # ------------------------------------------------------------------
    @staticmethod
    def _resolve_currency(booking: Booking, currency: Currency | None) -> Currency:
        """Default to the booking's currency; a mismatch is a money bug — a claim
        funds an SD capture, which is single-currency."""
        if currency is None:
            return booking.currency
        if currency.pk != booking.currency_id:
            raise DomainValidationError(
                field_errors={"currency": ["A damage claim must use the booking's currency."]}
            )
        return currency

    @staticmethod
    def _validate_amount(amount: Decimal) -> None:
        """Surface the model's `amount > 0` check constraint as a 400 field error
        rather than a 500 IntegrityError."""
        if amount <= 0:
            raise DomainValidationError(
                field_errors={"amount": ["Amount must be greater than zero."]}
            )
