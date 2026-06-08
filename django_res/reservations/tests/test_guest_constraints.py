"""DB-level integrity for `Guest` — the honest-NOT-NULL constraints.

Both constraints are scoped to `status=ACTIVE`; ARCHIVED/ANONYMIZED rows are
exempt so a dispositioned channel-less row (or a redacted one) is legal.
See django_res_design/people-model-cleanup.md.
"""

from __future__ import annotations

import pytest
from django.db import IntegrityError

from reservations.enums import ContactMethod, GuestStatus
from reservations.models import Guest

pytestmark = pytest.mark.django_db


def _guest(**kwargs: object) -> Guest:
    base: dict[str, object] = {"first_name": "A", "last_name": "B"}
    base.update(kwargs)
    return Guest.objects.create(**base)


# --- contactability ---------------------------------------------------------


def test_active_guest_with_no_channel_rejected() -> None:
    with pytest.raises(IntegrityError):
        _guest(email=None, phone="")


def test_phone_only_active_guest_allowed() -> None:
    guest = _guest(email=None, phone="+447911123456")
    assert guest.pk is not None


def test_email_only_active_guest_allowed() -> None:
    guest = _guest(email="a@b.com", phone="")
    assert guest.pk is not None


@pytest.mark.parametrize("status", [GuestStatus.ARCHIVED, GuestStatus.ANONYMIZED])
def test_inactive_guest_with_no_channel_allowed(status: GuestStatus) -> None:
    guest = _guest(email=None, phone="", status=status)
    assert guest.pk is not None


def test_empty_string_email_normalized_to_none() -> None:
    """`email=""` is the absence of an email, not a present-but-blank one.

    `save()` collapses it to NULL so `email__isnull` (and every contactability
    check keyed on it) reflects the truth across all write paths.
    """
    guest = _guest(email="", phone="+447911123456")
    guest.refresh_from_db()
    assert guest.email is None


def test_active_guest_with_empty_email_and_no_phone_rejected() -> None:
    """An empty-string email must not slip past the contactability CHECK.

    Without normalization `email=""` makes `email__isnull=False` true, so an
    uncontactable ACTIVE guest would be legal via the admin/ORM/bulk paths that
    bypass the serializer. `save()` normalizes "" → NULL so the DB CHECK bites.
    """
    with pytest.raises(IntegrityError):
        _guest(email="", phone="")


# --- actionable preference --------------------------------------------------


def test_active_email_preference_without_email_rejected() -> None:
    # Contactable by phone, so this isolates the preference constraint.
    with pytest.raises(IntegrityError):
        _guest(email=None, phone="+447911123456", contact_method=ContactMethod.EMAIL)


def test_active_phone_preference_without_phone_rejected() -> None:
    with pytest.raises(IntegrityError):
        _guest(email="a@b.com", phone="", contact_method=ContactMethod.PHONE)


def test_active_sms_preference_without_phone_rejected() -> None:
    with pytest.raises(IntegrityError):
        _guest(email="a@b.com", phone="", contact_method=ContactMethod.SMS)


def test_active_email_preference_with_email_allowed() -> None:
    guest = _guest(email="a@b.com", phone="", contact_method=ContactMethod.EMAIL)
    assert guest.pk is not None


def test_inactive_unactionable_preference_allowed() -> None:
    guest = _guest(
        email=None,
        phone="",
        contact_method=ContactMethod.EMAIL,
        status=GuestStatus.ARCHIVED,
    )
    assert guest.pk is not None
