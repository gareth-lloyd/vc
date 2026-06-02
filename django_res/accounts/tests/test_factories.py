"""Factory smoke tests for the accounts app."""

from __future__ import annotations

from typing import cast

import pytest

from accounts import factories, models
from core.enums import StaffRole

pytestmark = pytest.mark.django_db


def test_user_factory_sets_usable_password_and_unique_email() -> None:
    u1 = cast(models.User, factories.UserFactory())
    u2 = cast(models.User, factories.UserFactory())
    assert u1.email != u2.email
    assert u1.check_password("seed-password")
    assert u1.role in StaffRole.values


def test_contact_with_primary_email_and_phone() -> None:
    contact = cast(models.Contact, factories.ContactFactory())
    email = factories.ContactEmailFactory(contact=contact)
    phone = factories.ContactPhoneFactory(contact=contact)
    assert email.is_primary
    assert phone.is_primary
    assert contact.emails.count() == 1
