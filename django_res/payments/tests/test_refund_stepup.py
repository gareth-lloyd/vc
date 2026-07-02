"""Refund-execution TOTP step-up (GAP-057 Unit 3).

`POST /refunds/{id}:execute` is the money-out click. When TFA_ENFORCED is on,
executing requires a valid, single-use TOTP code from the acting user on every
call (freshness = the TOTP window + the replay guard from Unit 1). The check is
gated on TFA_ENFORCED so dev/test/seed stay ceremony-free; the ~existing execute
tests run flag-off and are unaffected. The system caller (actor=None) is exempt.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pyotp
import pytest
import structlog.testing
from django.contrib.auth.models import Permission
from django.test import override_settings

from accounts.enums import TfaMethod
from core.exceptions import InvalidTfaCode, TfaStepUpRequired
from payments.enums import (
    RefundPurposeTrack,
    RefundReasonCode,
    RefundStatus,
)
from payments.models import Payment, Refund
from payments.services.refund import RefundService


def _grant(user: Any, *codenames: str) -> None:
    for codename in codenames:
        user.user_permissions.add(Permission.objects.get(codename=codename))


def _enroll(user: Any) -> str:
    """Give `user` a live TOTP secret and return it."""
    secret = pyotp.random_base32()
    user.tfa_method = TfaMethod.TOTP
    user.tfa_secret = secret
    user.save(update_fields=["tfa_method", "tfa_secret"])
    return secret


@pytest.fixture
def paid_deposit(db: None, booking: Any, gbp: Any) -> Payment:
    from payments.enums import PaymentPurpose, PaymentStatus

    return Payment.objects.create(
        booking=booking,
        purpose=PaymentPurpose.DEPOSIT.value,
        status=PaymentStatus.SUCCEEDED.value,
        amount=Decimal("420.00"),
        currency=gbp,
    )


def _approved_refund(
    booking: Any, gbp: Any, requester: Any, approver: Any, paid: Payment
) -> Refund:
    refund = RefundService.request(
        booking=booking,
        amount=Decimal("50.00"),
        currency=gbp,
        purpose_track=RefundPurposeTrack.DEPOSIT.value,
        reason_code=RefundReasonCode.OVERPAYMENT.value,
        against_payment=paid,
        requested_by=requester,
    )
    RefundService.approve(refund, actor=approver)
    refund.refresh_from_db()
    return refund


@pytest.fixture
def paid_balance(db: None, booking: Any, gbp: Any) -> Payment:
    from payments.enums import PaymentPurpose, PaymentStatus

    return Payment.objects.create(
        booking=booking,
        purpose=PaymentPurpose.BALANCE.value,
        status=PaymentStatus.SUCCEEDED.value,
        amount=Decimal("980.00"),
        currency=gbp,
    )


@pytest.fixture
def executor(db: None) -> Any:
    from accounts.models import User

    actor = User.objects.create_user(email="executor@example.com", password="pw", is_staff=True)
    _grant(actor, "approve_refund", "execute_refund", "self_approve_refund")
    return actor


# --- flag off: no code required (existing behaviour) -----------------------


@pytest.mark.django_db
def test_execute_flag_off_needs_no_code(
    booking: Any, gbp: Any, user: Any, executor: Any, paid_deposit: Payment
) -> None:
    refund = _approved_refund(booking, gbp, user, executor, paid_deposit)

    RefundService.execute(refund, actor=executor)  # no tfa_code

    refund.refresh_from_db()
    assert refund.status == RefundStatus.EXECUTING.value


# --- flag on ---------------------------------------------------------------


@override_settings(TFA_ENFORCED=True)
@pytest.mark.django_db
def test_execute_system_caller_exempt(
    booking: Any, gbp: Any, user: Any, executor: Any, paid_deposit: Payment
) -> None:
    # actor=None is the documented system sentinel — no step-up.
    refund = _approved_refund(booking, gbp, user, executor, paid_deposit)

    RefundService.execute(refund, actor=None)

    refund.refresh_from_db()
    assert refund.status == RefundStatus.EXECUTING.value


@override_settings(TFA_ENFORCED=True)
@pytest.mark.django_db
def test_execute_missing_code_raises_stepup(
    booking: Any, gbp: Any, user: Any, executor: Any, paid_deposit: Payment
) -> None:
    _enroll(executor)
    refund = _approved_refund(booking, gbp, user, executor, paid_deposit)

    with pytest.raises(TfaStepUpRequired):
        RefundService.execute(refund, actor=executor)

    refund.refresh_from_db()
    assert refund.status == RefundStatus.APPROVED.value  # unchanged


@override_settings(TFA_ENFORCED=True)
@pytest.mark.django_db
def test_execute_invalid_code_raises_invalid(
    booking: Any, gbp: Any, user: Any, executor: Any, paid_deposit: Payment
) -> None:
    _enroll(executor)
    refund = _approved_refund(booking, gbp, user, executor, paid_deposit)

    with pytest.raises(InvalidTfaCode):
        RefundService.execute(refund, actor=executor, tfa_code="000000")

    refund.refresh_from_db()
    assert refund.status == RefundStatus.APPROVED.value


@override_settings(TFA_ENFORCED=True)
@pytest.mark.django_db
def test_execute_actor_not_enrolled_raises_stepup(
    booking: Any, gbp: Any, user: Any, executor: Any, paid_deposit: Payment
) -> None:
    # executor has no TOTP secret (only reachable with the flag on when a staff
    # user somehow reaches execute un-enrolled — belt and braces).
    refund = _approved_refund(booking, gbp, user, executor, paid_deposit)

    with pytest.raises(TfaStepUpRequired):
        RefundService.execute(refund, actor=executor, tfa_code="123456")


@override_settings(TFA_ENFORCED=True)
@pytest.mark.django_db
def test_execute_happy_path_with_fresh_code(
    booking: Any, gbp: Any, user: Any, executor: Any, paid_deposit: Payment
) -> None:
    secret = _enroll(executor)
    refund = _approved_refund(booking, gbp, user, executor, paid_deposit)
    code = pyotp.TOTP(secret).now()

    with structlog.testing.capture_logs() as logs:
        RefundService.execute(refund, actor=executor, tfa_code=code)

    refund.refresh_from_db()
    assert refund.status == RefundStatus.EXECUTING.value
    events = {log.get("event") for log in logs}
    assert "refund.stepup_verified" in events
    # The raw code is never logged.
    assert all(code not in str(log.values()) for log in logs)


@override_settings(TFA_ENFORCED=True)
@pytest.mark.django_db
def test_execute_same_code_twice_fails_second(
    booking: Any, gbp: Any, user: Any, executor: Any, paid_deposit: Payment, paid_balance: Payment
) -> None:
    secret = _enroll(executor)
    r1 = _approved_refund(booking, gbp, user, executor, paid_deposit)
    r2 = _approved_refund(booking, gbp, user, executor, paid_balance)
    code = pyotp.TOTP(secret).now()

    RefundService.execute(r1, actor=executor, tfa_code=code)
    with pytest.raises(InvalidTfaCode):
        RefundService.execute(r2, actor=executor, tfa_code=code)  # replay refused


@override_settings(TFA_ENFORCED=True)
@pytest.mark.django_db
def test_execute_idempotent_retry_of_executing_needs_no_code(
    booking: Any, gbp: Any, user: Any, executor: Any, paid_deposit: Payment
) -> None:
    # The step-up sits below the idempotency short-circuit, so a retry of an
    # already-EXECUTING refund returns without demanding a code.
    secret = _enroll(executor)
    refund = _approved_refund(booking, gbp, user, executor, paid_deposit)
    RefundService.execute(refund, actor=executor, tfa_code=pyotp.TOTP(secret).now())
    refund.refresh_from_db()
    assert refund.status == RefundStatus.EXECUTING.value

    # Retry with no code — must not raise.
    RefundService.execute(refund, actor=executor)
    refund.refresh_from_db()
    assert refund.status == RefundStatus.EXECUTING.value
