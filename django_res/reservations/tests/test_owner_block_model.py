"""Model-level checks for OwnerBlock."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, cast

import pytest
from django.db import IntegrityError

from accounts.factories import UserFactory
from accounts.models import User
from reservations.enums import OwnerBlockStatus
from reservations.models import OwnerBlock

if TYPE_CHECKING:
    from properties.models import Property

pytestmark = pytest.mark.django_db


def test_defaults_to_approved(property_: Property) -> None:
    block = OwnerBlock.objects.create(
        property=property_,
        created_by=cast(User, UserFactory()),
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 8),
    )
    assert block.status == OwnerBlockStatus.APPROVED


def test_rejects_inverted_date_range(property_: Property) -> None:
    with pytest.raises(IntegrityError):
        OwnerBlock.objects.create(
            property=property_,
            created_by=cast(User, UserFactory()),
            date_from=date(2026, 7, 8),
            date_to=date(2026, 7, 1),
        )
