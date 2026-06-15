"""Integration: BookingHold lifecycle lands AuditLog rows (FG-017).

The availability-blocking lifecycle (place → release) had no trail of who placed
or released a hold, frustrating inventory-dispute reconstruction (and BUG-005's
stale-hold diagnosis). `HoldService.release` goes through `hold.save()`, so the
pre_save trail captures the `released_at` transition.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

import pytest
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from core.models import AuditLog
from reservations.enums import BookingHoldReason
from reservations.models import BookingHold
from reservations.services.holds import HoldService

if TYPE_CHECKING:
    from properties.models import Property


@pytest.mark.django_db
def test_hold_release_writes_audit_row(property_: Property) -> None:
    hold = HoldService.place(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        expires_at=timezone.now() + timedelta(hours=1),
        reason=BookingHoldReason.MANUAL.value,
    )

    HoldService.release(hold)

    ct = ContentType.objects.get_for_model(BookingHold)
    rows = AuditLog.objects.filter(content_type=ct, object_id=str(hold.pk))
    released_rows = [r for r in rows if "released_at" in r.field_diffs]
    assert released_rows, "expected an AuditLog row capturing the hold release"
    old, new = released_rows[-1].field_diffs["released_at"]
    assert old is None
    assert new is not None


@pytest.mark.django_db
def test_hold_hard_delete_writes_tombstone_row(property_: Property) -> None:
    hold = HoldService.place(
        property=property_,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 8),
        expires_at=timezone.now() + timedelta(hours=1),
        reason=BookingHoldReason.MANUAL.value,
    )
    hold_pk = hold.pk

    hold.delete()

    ct = ContentType.objects.get_for_model(BookingHold)
    rows = AuditLog.objects.filter(content_type=ct, object_id=str(hold_pk))
    deleted = [r for r in rows if r.field_diffs.get("__deleted__")]
    assert deleted, "expected a __deleted__ tombstone row for the hard-deleted hold"
