"""The admin approve/decline actions drive OwnerBlockService."""

from __future__ import annotations

from datetime import timedelta
from typing import cast

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.http import HttpRequest
from django.test import RequestFactory
from django.utils import timezone

from accounts.factories import UserFactory
from accounts.models import User
from owners.enums import OwnerMembershipStatus
from owners.factories import OwnerMembershipFactory, OwnerOrganisationFactory
from owners.models import OwnerOrganisation
from properties.models import Property
from reservations.admin import OwnerBlockAdmin
from reservations.enums import OwnerBlockStatus
from reservations.models import OwnerBlock

pytestmark = pytest.mark.django_db


def _request(user: User) -> HttpRequest:
    request = RequestFactory().post("/admin/")
    request.user = user
    request.session = "session"  # type: ignore[assignment]
    request._messages = FallbackStorage(request)  # type: ignore[attr-defined]
    return request


def _pending(property_: Property) -> OwnerBlock:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    owner = cast(User, UserFactory(is_staff=False))
    OwnerMembershipFactory(organisation=org, user=owner, status=OwnerMembershipStatus.ACTIVE)
    start = timezone.localdate() + timedelta(days=15)
    return OwnerBlock.objects.create(
        property=property_,
        created_by=owner,
        date_from=start,
        date_to=start + timedelta(days=4),
    )


def test_admin_approve_action_places_hold(property_: Property) -> None:
    req = _pending(property_)
    admin = OwnerBlockAdmin(OwnerBlock, AdminSite())
    staff = cast(User, UserFactory())

    admin.approve_selected(_request(staff), OwnerBlock.objects.filter(pk=req.pk))

    req.refresh_from_db()
    assert req.status == OwnerBlockStatus.APPROVED.value
    assert req.resulting_hold is not None


def test_admin_decline_action(property_: Property) -> None:
    req = _pending(property_)
    admin = OwnerBlockAdmin(OwnerBlock, AdminSite())
    staff = cast(User, UserFactory())

    admin.decline_selected(_request(staff), OwnerBlock.objects.filter(pk=req.pk))

    req.refresh_from_db()
    assert req.status == OwnerBlockStatus.DECLINED.value
