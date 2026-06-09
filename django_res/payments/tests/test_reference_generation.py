"""Reference generation is DB-assigned, so every insert path gets a unique ref.

BUG-007: the original `save()`-only scheme left `reference=""` on any
`bulk_create` path (the second blank row violates the unique constraint), and
the "generate then check" happy path had a TOCTOU race. The fix moves
allocation into a Postgres sequence wired as the column's `db_default`, so the
database stamps the reference on *every* insert path — `save()`, `bulk_create`,
raw SQL — with no Python in the loop.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from payments.enums import PaymentPurpose
from payments.models import Payment

if TYPE_CHECKING:
    from pricing.models import Currency
    from reservations.models import Booking

pytestmark = pytest.mark.django_db


def _payment(booking: Booking, gbp: Currency, purpose: str) -> Payment:
    return Payment(
        booking=booking,
        purpose=purpose,
        amount=Decimal("100.00"),
        currency=gbp,
    )


def test_bulk_create_assigns_distinct_non_empty_references(booking: Booking, gbp: Currency) -> None:
    """`bulk_create` is the path the old save()-only scheme silently skipped."""
    Payment.objects.bulk_create(
        [
            _payment(booking, gbp, PaymentPurpose.DEPOSIT.value),
            _payment(booking, gbp, PaymentPurpose.BALANCE.value),
        ]
    )

    refs = list(Payment.objects.values_list("reference", flat=True))
    assert all(refs), f"blank reference slipped through: {refs!r}"
    assert len(set(refs)) == 2, f"duplicate references: {refs!r}"
    assert all(r.startswith("P-") for r in refs), refs


def test_create_populates_reference_in_memory_without_refresh(
    booking: Booking, gbp: Currency
) -> None:
    """Postgres returns the `db_default` value via `INSERT ... RETURNING`.

    Service callers (refund/SD/scheduler) read `.reference` straight off the
    returned instance, so a regression to the resolution path would break the
    create response without this guard. No `refresh_from_db` on purpose.
    """
    payment = Payment.objects.create(
        booking=booking,
        purpose=PaymentPurpose.DEPOSIT.value,
        amount=Decimal("100.00"),
        currency=gbp,
    )
    assert payment.reference.startswith("P-")


def test_bulk_create_populates_reference_in_memory_without_refresh(
    booking: Booking, gbp: Currency
) -> None:
    """`PaymentScheduler` relies on `bulk_create` returning resolved references."""
    created = Payment.objects.bulk_create([_payment(booking, gbp, PaymentPurpose.DEPOSIT.value)])
    assert created[0].reference.startswith("P-")


def test_explicit_reference_is_preserved(booking: Booking, gbp: Currency) -> None:
    """Loaders set a reference directly; the sequence must not override it."""
    payment = Payment.objects.create(
        booking=booking,
        purpose=PaymentPurpose.DEPOSIT.value,
        amount=Decimal("100.00"),
        currency=gbp,
        reference="P-LEGACY-1",
    )
    payment.refresh_from_db()
    assert payment.reference == "P-LEGACY-1"
