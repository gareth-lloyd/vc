"""Model-level checks for OwnerBlockRequest."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, cast

import pytest
from django.db import IntegrityError

from accounts.factories import UserFactory
from accounts.models import User
from reservations.enums import OwnerBlockRequestStatus
from reservations.models import OwnerBlockRequest

if TYPE_CHECKING:
    from properties.models import Property

pytestmark = pytest.mark.django_db


def test_defaults_to_pending(property_: Property) -> None:
    req = OwnerBlockRequest.objects.create(
        property=property_,
        requested_by=cast(User, UserFactory()),
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 8),
    )
    assert req.status == OwnerBlockRequestStatus.PENDING
    assert req.resulting_hold_id is None


def test_rejects_inverted_date_range(property_: Property) -> None:
    with pytest.raises(IntegrityError):
        OwnerBlockRequest.objects.create(
            property=property_,
            requested_by=cast(User, UserFactory()),
            date_from=date(2026, 7, 8),
            date_to=date(2026, 7, 1),
        )
