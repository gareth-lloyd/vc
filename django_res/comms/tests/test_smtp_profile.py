from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction

from accounts.models import User
from comms.enums import SmtpScope
from comms.models import SmtpProfile


@pytest.fixture
def user(db: None) -> User:
    return User.objects.create_user(email="agent@example.com", password="pw")


def _new_profile_kwargs(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "name": "System",
        "scope": SmtpScope.SYSTEM,
        "owner": None,
        "host": "smtp.example.com",
        "port": 587,
        "username": "user",
        "encrypted_password": "secret",
        "from_email": "noreply@example.com",
    }
    base.update(overrides)
    return base


@pytest.mark.django_db
def test_personal_profile_requires_owner() -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        SmtpProfile.objects.create(
            **_new_profile_kwargs(
                name="Alice",
                scope=SmtpScope.PERSONAL,
                owner=None,
            )
        )


@pytest.mark.django_db
def test_system_profile_must_not_have_owner(user: User) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        SmtpProfile.objects.create(
            **_new_profile_kwargs(
                name="System",
                scope=SmtpScope.SYSTEM,
                owner=user,
            )
        )


@pytest.mark.django_db
def test_only_one_active_system_profile() -> None:
    SmtpProfile.objects.create(**_new_profile_kwargs(name="Primary"))

    with pytest.raises(IntegrityError), transaction.atomic():
        SmtpProfile.objects.create(**_new_profile_kwargs(name="Secondary"))


@pytest.mark.django_db
def test_inactive_system_profile_does_not_collide() -> None:
    SmtpProfile.objects.create(**_new_profile_kwargs(name="Primary", is_active=False))
    # No exception: only active SYSTEM profiles are constrained as unique.
    SmtpProfile.objects.create(**_new_profile_kwargs(name="Replacement"))


@pytest.mark.django_db
def test_only_one_active_personal_profile_per_user(user: User) -> None:
    SmtpProfile.objects.create(
        **_new_profile_kwargs(
            name="Alice primary",
            scope=SmtpScope.PERSONAL,
            owner=user,
            from_email="alice@example.com",
        )
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        SmtpProfile.objects.create(
            **_new_profile_kwargs(
                name="Alice second",
                scope=SmtpScope.PERSONAL,
                owner=user,
                from_email="alice2@example.com",
            )
        )
