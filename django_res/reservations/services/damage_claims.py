"""DamageClaim service — the sanctioned write path for damages claims.

`DamageClaimService` owns the claim's small set of invariants: the currency is
pinned to the booking's (a claim funds an SD capture, which is single-currency),
the amount is strictly positive (surfaced as a 400 rather than the DB check
constraint's 500), and the `created_by`/`updated_by` actor is stamped. The
AuditLog trail rides the model's `track()` registration (BUG-008), so `.save()`
/ `.delete()` here are audited without extra plumbing.

Lifecycle is the `DamageClaimStatus` enum: `withdraw()` is the operator "cancel"
(→ WITHDRAWN); a true mistake can still be hard-deleted (the SD FK is SET_NULL,
so the deposit's money trail survives). The approval state machine and the
SD-capture wiring land with workflow 8/17.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.db import transaction

from core.exceptions import DomainValidationError
from reservations.enums import DamageClaimStatus
from reservations.models import DamageClaim

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
    def withdraw(cls, claim: DamageClaim, *, actor: Any = None) -> DamageClaim:
        claim.status = DamageClaimStatus.WITHDRAWN.value
        claim.updated_by = actor
        claim.save(update_fields=["status", "updated_by", "updated_at"])
        return claim

    @classmethod
    @transaction.atomic
    def delete(cls, claim: DamageClaim, *, actor: Any = None) -> None:
        claim.delete()

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
