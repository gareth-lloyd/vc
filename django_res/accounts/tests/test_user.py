from __future__ import annotations

import pytest

from accounts.models import User
from core.enums import StaffRole


@pytest.mark.django_db
def test_create_user_normalises_email() -> None:
    user = User.objects.create_user(email="Owner@Example.com", password="secret")

    assert user.email == "owner@example.com"
    assert user.role == StaffRole.VIEWER
    assert user.check_password("secret")


@pytest.mark.django_db
def test_create_superuser() -> None:
    user = User.objects.create_superuser(email="root@example.com", password="secret")

    assert user.is_superuser
    assert user.is_staff
    assert user.role == StaffRole.ADMIN
