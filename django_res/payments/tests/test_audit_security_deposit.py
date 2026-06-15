"""Integration: a SecurityDeposit status transition lands an AuditLog row (FG-014)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from django.contrib.contenttypes.models import ContentType

from core.models import AuditLog
from payments.enums import SecurityDepositKind, SecurityDepositStatus
from payments.models import SecurityDeposit


@pytest.mark.django_db
def test_security_deposit_status_transition_writes_audit_row(booking: Any, gbp: Any) -> None:
    sd = SecurityDeposit.objects.create(
        booking=booking,
        kind=SecurityDepositKind.PRE_AUTH_HOLD.value,
        amount=Decimal("500.00"),
        currency=gbp,
        status=SecurityDepositStatus.AWAITING_DETAILS.value,
    )

    sd.transition_to_pre_authed()

    ct = ContentType.objects.get_for_model(SecurityDeposit)
    rows = AuditLog.objects.filter(content_type=ct, object_id=str(sd.pk))
    status_rows = [r for r in rows if "status" in r.field_diffs]
    assert status_rows, "expected an AuditLog row capturing the SD status change"
    pair = status_rows[-1].field_diffs["status"]
    assert pair == [
        SecurityDepositStatus.AWAITING_DETAILS.value,
        SecurityDepositStatus.PRE_AUTHED.value,
    ]
