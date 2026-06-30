"""Tests for `DamageClaimService` — the sanctioned write path for damage claims.

The service pins the currency to the booking's, refuses a non-positive amount
with a clean 400 (not a 500 IntegrityError), stamps `created_by`/`updated_by`,
and carries claims through their `OPEN → WITHDRAWN` lifecycle. Audit rows ride
the model's `track()` registration (BUG-008), so they are not re-asserted here.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from core.exceptions import DomainValidationError, InvalidTransition
from pricing.models import Currency
from reservations.enums import DamageClaimStatus
from reservations.factories import make_occupying_booking
from reservations.models import DamageClaim
from reservations.services.damage_claims import DamageClaimService

if TYPE_CHECKING:
    from accounts.models import Person, User
    from properties.models import Property
    from reservations.models import Booking, TermsVersion


@pytest.fixture
def booking(property_: Property, customer: Person, gbp: Currency, terms: TermsVersion) -> Booking:
    return make_occupying_booking(
        property=property_,
        person=customer,
        currency=gbp,
        terms=terms,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
    )


@pytest.fixture
def actor(db: None) -> User:
    from accounts.models import User

    return User.objects.create_user(
        is_staff=True,
        email="dc-actor@example.com",
        password="x",
    )


@pytest.mark.django_db
def test_create_defaults_currency_and_status(booking: Booking, actor: User) -> None:
    claim = DamageClaimService.create(
        booking,
        amount=Decimal("250.00"),
        description="Broken bedroom window",
        actor=actor,
    )

    assert claim.pk is not None
    assert claim.currency_id == booking.currency_id  # defaulted to the booking's
    assert claim.status == DamageClaimStatus.OPEN.value
    assert claim.amount == Decimal("250.00")
    assert claim.itemized_lines == []
    assert claim.created_by_id == actor.pk
    assert claim.updated_by_id == actor.pk


@pytest.mark.django_db
def test_create_accepts_itemized_lines(booking: Booking) -> None:
    lines = [{"label": "Sofa", "amount": "200.00"}, {"label": "Rug", "amount": "50.00"}]
    claim = DamageClaimService.create(
        booking,
        amount=Decimal("250.00"),
        description="Lounge damage",
        itemized_lines=lines,
    )

    assert claim.itemized_lines == lines


@pytest.mark.django_db
def test_create_rejects_mismatched_currency(booking: Booking) -> None:
    eur = Currency.objects.create(code="EUR", name="Euro", symbol="€")

    with pytest.raises(DomainValidationError) as exc:
        DamageClaimService.create(
            booking,
            amount=Decimal("100.00"),
            description="Wrong currency",
            currency=eur,
        )

    assert "currency" in exc.value.field_errors


@pytest.mark.django_db
@pytest.mark.parametrize("bad", [Decimal("0.00"), Decimal("-5.00")])
def test_create_rejects_non_positive_amount(booking: Booking, bad: Decimal) -> None:
    # A clean 400, never a 500 IntegrityError from the DB check constraint.
    with pytest.raises(DomainValidationError) as exc:
        DamageClaimService.create(booking, amount=bad, description="Bad amount")

    assert "amount" in exc.value.field_errors
    assert not DamageClaim.objects.exists()


@pytest.mark.django_db
def test_update_changes_fields_and_stamps_actor(booking: Booking, actor: User) -> None:
    claim = DamageClaimService.create(booking, amount=Decimal("100.00"), description="Initial")

    updated = DamageClaimService.update(
        claim, amount=Decimal("175.00"), description="Revised", actor=actor
    )

    updated.refresh_from_db()
    assert updated.amount == Decimal("175.00")
    assert updated.description == "Revised"
    assert updated.updated_by_id == actor.pk


@pytest.mark.django_db
def test_update_rejects_mismatched_currency(booking: Booking) -> None:
    eur = Currency.objects.create(code="EUR", name="Euro", symbol="€")
    claim = DamageClaimService.create(booking, amount=Decimal("100.00"), description="x")

    with pytest.raises(DomainValidationError):
        DamageClaimService.update(claim, currency=eur)


@pytest.mark.django_db
def test_update_rejects_non_positive_amount(booking: Booking) -> None:
    claim = DamageClaimService.create(booking, amount=Decimal("100.00"), description="x")

    with pytest.raises(DomainValidationError):
        DamageClaimService.update(claim, amount=Decimal("0.00"))


@pytest.mark.django_db
def test_withdraw_sets_status(booking: Booking, actor: User) -> None:
    claim = DamageClaimService.create(booking, amount=Decimal("100.00"), description="x")

    withdrawn = DamageClaimService.withdraw(claim, actor=actor)

    withdrawn.refresh_from_db()
    assert withdrawn.status == DamageClaimStatus.WITHDRAWN.value
    assert withdrawn.updated_by_id == actor.pk


# ---------------------------------------------------------------------------
# Approval state machine (OPEN → APPROVED → SETTLED, + WITHDRAWN)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_approve_open_claim(booking: Booking, actor: User) -> None:
    claim = DamageClaimService.create(booking, amount=Decimal("100.00"), description="x")

    approved = DamageClaimService.approve(claim, actor=actor)

    approved.refresh_from_db()
    assert approved.status == DamageClaimStatus.APPROVED.value
    assert approved.updated_by_id == actor.pk


@pytest.mark.django_db
def test_settle_from_approved(booking: Booking, actor: User) -> None:
    claim = DamageClaimService.create(booking, amount=Decimal("100.00"), description="x")
    DamageClaimService.approve(claim, actor=actor)

    settled = DamageClaimService.settle(claim, actor=actor)

    settled.refresh_from_db()
    assert settled.status == DamageClaimStatus.SETTLED.value
    assert settled.updated_by_id == actor.pk


@pytest.mark.django_db
def test_settle_directly_from_open(booking: Booking, actor: User) -> None:
    # Capture can settle a never-approved claim (threshold approval is deferred).
    claim = DamageClaimService.create(booking, amount=Decimal("100.00"), description="x")

    settled = DamageClaimService.settle(claim, actor=actor)

    settled.refresh_from_db()
    assert settled.status == DamageClaimStatus.SETTLED.value


@pytest.mark.django_db
def test_withdraw_from_approved(booking: Booking, actor: User) -> None:
    claim = DamageClaimService.create(booking, amount=Decimal("100.00"), description="x")
    DamageClaimService.approve(claim, actor=actor)

    withdrawn = DamageClaimService.withdraw(claim, actor=actor)

    withdrawn.refresh_from_db()
    assert withdrawn.status == DamageClaimStatus.WITHDRAWN.value


@pytest.mark.django_db
def test_approve_settled_claim_is_invalid(booking: Booking, actor: User) -> None:
    claim = DamageClaimService.create(booking, amount=Decimal("100.00"), description="x")
    DamageClaimService.settle(claim, actor=actor)

    with pytest.raises(InvalidTransition):
        DamageClaimService.approve(claim, actor=actor)


@pytest.mark.django_db
def test_withdraw_settled_claim_is_invalid(booking: Booking, actor: User) -> None:
    claim = DamageClaimService.create(booking, amount=Decimal("100.00"), description="x")
    DamageClaimService.settle(claim, actor=actor)

    with pytest.raises(InvalidTransition):
        DamageClaimService.withdraw(claim, actor=actor)


@pytest.mark.django_db
def test_settle_withdrawn_claim_is_invalid(booking: Booking, actor: User) -> None:
    claim = DamageClaimService.create(booking, amount=Decimal("100.00"), description="x")
    DamageClaimService.withdraw(claim, actor=actor)

    with pytest.raises(InvalidTransition):
        DamageClaimService.settle(claim, actor=actor)


@pytest.mark.django_db
def test_update_refused_on_settled_claim(booking: Booking, actor: User) -> None:
    claim = DamageClaimService.create(booking, amount=Decimal("100.00"), description="x")
    DamageClaimService.settle(claim, actor=actor)

    with pytest.raises(DomainValidationError):
        DamageClaimService.update(claim, amount=Decimal("175.00"), actor=actor)


@pytest.mark.django_db
def test_update_refused_on_withdrawn_claim(booking: Booking, actor: User) -> None:
    claim = DamageClaimService.create(booking, amount=Decimal("100.00"), description="x")
    DamageClaimService.withdraw(claim, actor=actor)

    with pytest.raises(DomainValidationError):
        DamageClaimService.update(claim, amount=Decimal("175.00"), actor=actor)


@pytest.mark.django_db
def test_update_allowed_on_approved_claim(booking: Booking, actor: User) -> None:
    claim = DamageClaimService.create(booking, amount=Decimal("100.00"), description="x")
    DamageClaimService.approve(claim, actor=actor)

    updated = DamageClaimService.update(claim, amount=Decimal("175.00"), actor=actor)

    updated.refresh_from_db()
    assert updated.amount == Decimal("175.00")


@pytest.mark.django_db
def test_delete_hard_removes_the_row(booking: Booking) -> None:
    claim = DamageClaimService.create(booking, amount=Decimal("100.00"), description="x")

    DamageClaimService.delete(claim)

    assert not DamageClaim.objects.filter(pk=claim.pk).exists()
