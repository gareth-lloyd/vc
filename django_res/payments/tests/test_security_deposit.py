"""Tests for the `SecurityDeposit` workflow + `SecurityDepositService`."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

import pytest

from payments.enums import (
    PaymentMethod,
    PaymentPurpose,
    PaymentStatus,
    SecurityDepositKind,
    SecurityDepositStatus,
)
from payments.models import Payment, SecurityDeposit
from payments.services.security_deposit import SecurityDepositService

if TYPE_CHECKING:
    from reservations.models import DamageClaim


@pytest.mark.django_db
def test_create_for_booking__is_idempotent(booking: Any, property_: Any) -> None:
    """A second `create_for_booking` returns the existing SD, never a duplicate.

    `create_for_booking` is reachable from the booking-creation signal and the
    scheduler, so a re-entry must short-circuit — two active SECURITY_DEPOSIT
    rows per booking would break the one-active-per-booking invariant (BUG-006).
    """
    from decimal import Decimal

    from properties.models.finance import PropertyFinance

    finance, _ = PropertyFinance.objects.get_or_create(property=property_)
    finance.security_deposit_required = True
    finance.security_deposit_amount = Decimal("500.00")
    finance.security_deposit_calculation_type = "fixed"
    finance.save(
        update_fields=[
            "security_deposit_required",
            "security_deposit_amount",
            "security_deposit_calculation_type",
        ]
    )
    from reservations.models import Booking

    booking = Booking.objects.get(pk=booking.pk)

    first = SecurityDepositService.create_for_booking(booking)
    second = SecurityDepositService.create_for_booking(booking)

    assert first is not None
    assert second is not None
    assert second.pk == first.pk
    assert SecurityDeposit.objects.filter(booking=booking).count() == 1


@pytest.mark.django_db
def test_create_for_booking__percent_base_includes_charge_items(
    booking: Any, property_: Any, gbp: Any
) -> None:
    """A percent SD sizes against the same charges-inclusive total the
    deposit/balance schedule uses — not bare `balance_due`. 10% of
    (1400 + 200) = 160, not 140.
    """
    from properties.models.finance import PropertyFinance
    from reservations.models import Booking, BookingChargeItem

    finance, _ = PropertyFinance.objects.get_or_create(property=property_)
    finance.security_deposit_required = True
    finance.security_deposit_amount = Decimal("10.00")
    finance.security_deposit_calculation_type = "percent"
    finance.save(
        update_fields=[
            "security_deposit_required",
            "security_deposit_amount",
            "security_deposit_calculation_type",
        ]
    )
    booking = Booking.objects.get(pk=booking.pk)
    BookingChargeItem.objects.create(
        booking=booking, label="Heating", amount=Decimal("200.00"), currency=gbp
    )

    sd = SecurityDepositService.create_for_booking(booking)

    assert sd is not None
    assert sd.amount == Decimal("160.00")


@pytest.fixture
def pre_auth_sd(db: None, booking: Any, gbp: Any) -> SecurityDeposit:
    return SecurityDeposit.objects.create(
        booking=booking,
        kind=SecurityDepositKind.PRE_AUTH_HOLD.value,
        amount=Decimal("500.00"),
        currency=gbp,
        status=SecurityDepositStatus.AWAITING_DETAILS.value,
    )


@pytest.fixture
def bt_sd(db: None, booking: Any, gbp: Any) -> SecurityDeposit:
    return SecurityDeposit.objects.create(
        booking=booking,
        kind=SecurityDepositKind.BT_REFUNDABLE.value,
        amount=Decimal("500.00"),
        currency=gbp,
        status=SecurityDepositStatus.AWAITING_BT.value,
    )


@pytest.mark.django_db
def test_pre_auth_path__hold_release(
    pre_auth_sd: SecurityDeposit,
    booking: Any,
) -> None:
    SecurityDepositService.hold(
        pre_auth_sd,
        gateway_response={
            "provider": "flywire",
            "provider_reference": "flw-123",
            "hold_expires_at": datetime(2026, 8, 1, tzinfo=UTC),
        },
        actor=None,
    )
    pre_auth_sd.refresh_from_db()
    assert pre_auth_sd.status == SecurityDepositStatus.PRE_AUTHED.value
    assert pre_auth_sd.hold_expires_at is not None

    # `:hold` mints a Payment(SECURITY_DEPOSIT, SUCCEEDED).
    payment = Payment.objects.get(
        booking=booking,
        purpose=PaymentPurpose.SECURITY_DEPOSIT.value,
    )
    assert payment.status == PaymentStatus.SUCCEEDED.value
    assert payment.meta == {"security_deposit_id": pre_auth_sd.pk, "kind": "PRE_AUTH_HOLD"}

    SecurityDepositService.release(pre_auth_sd, actor=None)
    pre_auth_sd.refresh_from_db()
    assert pre_auth_sd.status == SecurityDepositStatus.RELEASED.value
    assert pre_auth_sd.released_at is not None


@pytest.fixture
def damage_claim(booking: Any, gbp: Any) -> DamageClaim:
    """A DamageClaim on the same booking as the SD fixtures, for capture."""
    from reservations.factories import DamageClaimFactory

    return cast("DamageClaim", DamageClaimFactory(booking=booking, currency=gbp))


@pytest.mark.django_db
def test_pre_auth_path__claim_captures(
    pre_auth_sd: SecurityDeposit,
    damage_claim: DamageClaim,
) -> None:
    SecurityDepositService.hold(
        pre_auth_sd,
        gateway_response={"provider": "flywire"},
        actor=None,
    )
    SecurityDepositService.claim(
        pre_auth_sd,
        damage_claim=damage_claim,
        captured_amount=Decimal("250.00"),
        actor=None,
    )
    pre_auth_sd.refresh_from_db()
    assert pre_auth_sd.status == SecurityDepositStatus.CAPTURED.value
    assert pre_auth_sd.captured_amount == Decimal("250.00")
    assert pre_auth_sd.damage_claim_id == damage_claim.pk


# --- wf8: capture settles the linked claim ------------------------------------


@pytest.mark.django_db
def test_capture_settles_an_open_claim(
    pre_auth_sd: SecurityDeposit, damage_claim: DamageClaim
) -> None:
    """The capture is the settlement: linking an OPEN claim moves it to SETTLED."""
    from reservations.enums import DamageClaimStatus

    SecurityDepositService.hold(pre_auth_sd, gateway_response={"provider": "flywire"}, actor=None)
    SecurityDepositService.claim(
        pre_auth_sd, damage_claim=damage_claim, captured_amount=Decimal("250.00"), actor=None
    )

    damage_claim.refresh_from_db()
    assert damage_claim.status == DamageClaimStatus.SETTLED.value


@pytest.mark.django_db
def test_capture_settles_an_approved_claim(
    pre_auth_sd: SecurityDeposit, damage_claim: DamageClaim
) -> None:
    from reservations.enums import DamageClaimStatus
    from reservations.services.damage_claims import DamageClaimService

    DamageClaimService.approve(damage_claim, actor=None)
    SecurityDepositService.hold(pre_auth_sd, gateway_response={"provider": "flywire"}, actor=None)
    SecurityDepositService.claim(
        pre_auth_sd, damage_claim=damage_claim, captured_amount=Decimal("250.00"), actor=None
    )

    damage_claim.refresh_from_db()
    assert damage_claim.status == DamageClaimStatus.SETTLED.value


@pytest.mark.django_db
def test_partial_refund_capture_settles_the_claim(
    bt_sd: SecurityDeposit, damage_claim: DamageClaim
) -> None:
    """The HELD → PARTIALLY_REFUNDED branch settles the claim too."""
    from reservations.enums import DamageClaimStatus

    SecurityDepositService.mark_paid(
        bt_sd,
        amount=Decimal("500.00"),
        paid_at=datetime(2026, 4, 1, 12, 0, tzinfo=UTC),
        method=PaymentMethod.BANK_TRANSFER.value,
        reference="wire-001",
        actor=None,
    )
    SecurityDepositService.claim(
        bt_sd, damage_claim=damage_claim, captured_amount=Decimal("200.00"), actor=None
    )

    damage_claim.refresh_from_db()
    assert damage_claim.status == DamageClaimStatus.SETTLED.value


@pytest.mark.django_db
def test_capture_against_an_already_settled_claim_does_not_raise(
    pre_auth_sd: SecurityDeposit, damage_claim: DamageClaim
) -> None:
    """The OPEN/APPROVED guard makes a capture linking an already-SETTLED claim
    a no-op rather than an InvalidTransition (SETTLED is terminal)."""
    from reservations.enums import DamageClaimStatus

    damage_claim.status = DamageClaimStatus.SETTLED.value
    damage_claim.save(update_fields=["status"])

    SecurityDepositService.hold(pre_auth_sd, gateway_response={"provider": "flywire"}, actor=None)
    # Must not raise even though the linked claim cannot transition.
    SecurityDepositService.claim(
        pre_auth_sd, damage_claim=damage_claim, captured_amount=Decimal("250.00"), actor=None
    )

    pre_auth_sd.refresh_from_db()
    assert pre_auth_sd.status == SecurityDepositStatus.CAPTURED.value
    damage_claim.refresh_from_db()
    assert damage_claim.status == DamageClaimStatus.SETTLED.value


@pytest.mark.django_db
def test_capture_leaves_a_withdrawn_claim_withdrawn(
    pre_auth_sd: SecurityDeposit, damage_claim: DamageClaim
) -> None:
    """A WITHDRAWN linked claim is not silently revived to SETTLED by a capture."""
    from reservations.enums import DamageClaimStatus
    from reservations.services.damage_claims import DamageClaimService

    DamageClaimService.withdraw(damage_claim, actor=None)
    SecurityDepositService.hold(pre_auth_sd, gateway_response={"provider": "flywire"}, actor=None)
    SecurityDepositService.claim(
        pre_auth_sd, damage_claim=damage_claim, captured_amount=Decimal("250.00"), actor=None
    )

    damage_claim.refresh_from_db()
    assert damage_claim.status == DamageClaimStatus.WITHDRAWN.value


# --- BUG-008: the damage_claim link is a real FK ------------------------------


@pytest.mark.django_db
def test_deleting_a_damage_claim_nulls_the_sd_link(
    pre_auth_sd: SecurityDeposit, damage_claim: DamageClaim
) -> None:
    """on_delete=SET_NULL: a claim can be hard-deleted without dragging the
    SD's money history down; the link just nulls out."""
    SecurityDepositService.hold(pre_auth_sd, gateway_response={"provider": "flywire"}, actor=None)
    SecurityDepositService.claim(
        pre_auth_sd, damage_claim=damage_claim, captured_amount=Decimal("100.00"), actor=None
    )
    pre_auth_sd.refresh_from_db()
    assert pre_auth_sd.damage_claim_id == damage_claim.pk

    damage_claim.delete()

    pre_auth_sd.refresh_from_db()
    assert pre_auth_sd.damage_claim_id is None
    # The captured_amount audit survives the claim's deletion.
    assert pre_auth_sd.captured_amount == Decimal("100.00")


@pytest.mark.django_db
def test_claim_resolves_a_raw_pk(pre_auth_sd: SecurityDeposit, damage_claim: DamageClaim) -> None:
    """The operator API passes a raw PK; the service resolves it to the row."""
    SecurityDepositService.hold(pre_auth_sd, gateway_response={"provider": "flywire"}, actor=None)
    SecurityDepositService.claim(
        pre_auth_sd, damage_claim=damage_claim.pk, captured_amount=Decimal("100.00"), actor=None
    )
    pre_auth_sd.refresh_from_db()
    assert pre_auth_sd.damage_claim_id == damage_claim.pk


@pytest.mark.django_db
def test_claim_with_unknown_pk_is_a_clean_validation_error(
    pre_auth_sd: SecurityDeposit,
) -> None:
    """A bad PK is a 400 DomainValidationError raised before any capture write,
    not a 500 IntegrityError part-way through the transaction."""
    from core.exceptions import DomainValidationError

    SecurityDepositService.hold(pre_auth_sd, gateway_response={"provider": "flywire"}, actor=None)
    with pytest.raises(DomainValidationError):
        SecurityDepositService.claim(
            pre_auth_sd, damage_claim=999_999, captured_amount=Decimal("100.00"), actor=None
        )

    pre_auth_sd.refresh_from_db()
    assert pre_auth_sd.status == SecurityDepositStatus.PRE_AUTHED.value
    assert pre_auth_sd.captured_amount is None


@pytest.mark.django_db
def test_claim_with_non_numeric_damage_claim_is_a_clean_validation_error(
    pre_auth_sd: SecurityDeposit,
) -> None:
    """A non-coercible JSON value (`request.data['damage_claim'] == 'abc'`) is a
    400, not the ValueError-mapped 500 the bare DoesNotExist catch would leave."""
    from core.exceptions import DomainValidationError

    SecurityDepositService.hold(pre_auth_sd, gateway_response={"provider": "flywire"}, actor=None)
    with pytest.raises(DomainValidationError):
        SecurityDepositService.claim(
            pre_auth_sd, damage_claim="abc", captured_amount=Decimal("100.00"), actor=None
        )


@pytest.mark.django_db
def test_claim_rejects_a_damage_claim_from_a_different_booking(
    pre_auth_sd: SecurityDeposit, property_: Any, customer: Any, gbp: Any, terms: Any
) -> None:
    """A claim must belong to the deposit's own booking — otherwise a capture
    could be justified by an unrelated booking's damages."""
    from datetime import date, timedelta

    from core.exceptions import DomainValidationError
    from reservations.factories import DamageClaimFactory, make_occupying_booking

    other_booking = make_occupying_booking(
        property=property_,
        person=customer,
        currency=gbp,
        terms=terms,
        date_from=date.today() + timedelta(days=300),
        date_to=date.today() + timedelta(days=307),
    )
    other_claim = DamageClaimFactory(booking=other_booking, currency=gbp)

    SecurityDepositService.hold(pre_auth_sd, gateway_response={"provider": "flywire"}, actor=None)
    with pytest.raises(DomainValidationError):
        SecurityDepositService.claim(
            pre_auth_sd, damage_claim=other_claim, captured_amount=Decimal("100.00"), actor=None
        )


@pytest.mark.django_db
def test_pre_auth_path__expiry_transition(
    pre_auth_sd: SecurityDeposit,
) -> None:
    SecurityDepositService.hold(
        pre_auth_sd,
        gateway_response={"provider": "flywire"},
        actor=None,
    )
    SecurityDepositService.expire(pre_auth_sd, actor=None)
    pre_auth_sd.refresh_from_db()
    assert pre_auth_sd.status == SecurityDepositStatus.EXPIRED.value


@pytest.mark.django_db
def test_bt_path__mark_paid_then_release(
    bt_sd: SecurityDeposit,
    booking: Any,
) -> None:
    SecurityDepositService.mark_paid(
        bt_sd,
        amount=Decimal("500.00"),
        paid_at=datetime(2026, 4, 1, 12, 0, tzinfo=UTC),
        method=PaymentMethod.BANK_TRANSFER.value,
        reference="wire-001",
        actor=None,
    )
    bt_sd.refresh_from_db()
    assert bt_sd.status == SecurityDepositStatus.HELD.value

    payment = Payment.objects.get(
        booking=booking,
        purpose=PaymentPurpose.SECURITY_DEPOSIT.value,
    )
    assert payment.status == PaymentStatus.SUCCEEDED.value
    assert payment.provider_reference == "wire-001"

    SecurityDepositService.release(bt_sd, actor=None)
    bt_sd.refresh_from_db()
    assert bt_sd.status == SecurityDepositStatus.REFUNDED.value
    assert bt_sd.refunded_amount == Decimal("500.00")


# ----------------------------------------------------------------------
# Kind guards — typed domain errors, not bare ValueError (BUG-011)
# ----------------------------------------------------------------------
@pytest.mark.django_db
def test_hold__wrong_kind_raises_typed_domain_error(bt_sd: SecurityDeposit) -> None:
    from core.exceptions import InvalidSecurityDepositKind

    with pytest.raises(InvalidSecurityDepositKind):
        SecurityDepositService.hold(bt_sd, gateway_response={}, actor=None)
    bt_sd.refresh_from_db()
    assert bt_sd.status == SecurityDepositStatus.AWAITING_BT.value


@pytest.mark.django_db
def test_mark_paid__wrong_kind_raises_typed_domain_error(
    pre_auth_sd: SecurityDeposit,
) -> None:
    from core.exceptions import InvalidSecurityDepositKind

    with pytest.raises(InvalidSecurityDepositKind):
        SecurityDepositService.mark_paid(
            pre_auth_sd,
            amount=Decimal("500.00"),
            paid_at=datetime(2026, 4, 1, 12, 0, tzinfo=UTC),
            method=PaymentMethod.BANK_TRANSFER.value,
            reference="wire-001",
            actor=None,
        )
    pre_auth_sd.refresh_from_db()
    assert pre_auth_sd.status == SecurityDepositStatus.AWAITING_DETAILS.value


# ----------------------------------------------------------------------
# Structured logging — the SD money path emits the op triples (BUG-011)
# ----------------------------------------------------------------------
@pytest.mark.django_db
def test_security_deposit_service_emits_structured_events(
    pre_auth_sd: SecurityDeposit,
    booking: Any,
) -> None:
    """hold/release emit the `security_deposit.*` op triples.

    The SD state machine is money movement — losing its structured
    observability would be a silent regression, so we pin the success lines
    and the key fields (security_deposit_id / amount / currency) riding on
    them. Mirrors `test_refund_service_emits_structured_events`.
    """
    from structlog.testing import capture_logs

    with capture_logs() as logs:
        SecurityDepositService.hold(
            pre_auth_sd,
            gateway_response={"provider": "flywire", "provider_reference": "flw-1"},
            actor=None,
        )
        SecurityDepositService.release(pre_auth_sd, actor=None)

    held = next(e for e in logs if e["event"] == "security_deposit.hold.succeeded")
    assert held["security_deposit_id"] == pre_auth_sd.pk
    assert held["booking_id"] == booking.pk
    assert held["amount"] == "500.00"
    assert held["currency"] == "GBP"

    released = next(e for e in logs if e["event"] == "security_deposit.release.succeeded")
    assert released["security_deposit_id"] == pre_auth_sd.pk


@pytest.mark.django_db
def test_bt_mark_paid_and_claim_emit_structured_events(
    bt_sd: SecurityDeposit, damage_claim: DamageClaim
) -> None:
    from structlog.testing import capture_logs

    with capture_logs() as logs:
        SecurityDepositService.mark_paid(
            bt_sd,
            amount=Decimal("500.00"),
            paid_at=datetime(2026, 4, 1, 12, 0, tzinfo=UTC),
            method=PaymentMethod.BANK_TRANSFER.value,
            reference="wire-001",
            actor=None,
        )
        SecurityDepositService.claim(
            bt_sd,
            damage_claim=damage_claim,
            captured_amount=Decimal("150.00"),
            actor=None,
        )

    paid = next(e for e in logs if e["event"] == "security_deposit.mark_paid.succeeded")
    assert paid["security_deposit_id"] == bt_sd.pk
    assert paid["amount"] == "500.00"

    claimed = next(e for e in logs if e["event"] == "security_deposit.claim.succeeded")
    assert claimed["security_deposit_id"] == bt_sd.pk
    assert claimed["captured_amount"] == "150.00"
