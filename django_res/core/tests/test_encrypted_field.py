"""EncryptedTextField round-trip smoke test.

Uses ``accounts.User.tfa_secret`` (the only concrete model field of type
``EncryptedTextField`` currently in the schema) so we exercise the real
Django save / load path without inventing a throwaway model just for tests.
"""

from __future__ import annotations

import pytest
from django.db import connection

from accounts.models import User


@pytest.mark.django_db
def test_encrypted_text_field_round_trip() -> None:
    user = User.objects.create_user(email="enc@example.com", password="pw")
    user.tfa_secret = "JBSWY3DPEHPK3PXP"
    user.save(update_fields=["tfa_secret"])

    reloaded = User.objects.get(pk=user.pk)
    assert reloaded.tfa_secret == "JBSWY3DPEHPK3PXP"


@pytest.mark.django_db
def test_encrypted_text_field_stores_ciphertext_on_disk() -> None:
    user = User.objects.create_user(email="enc2@example.com", password="pw")
    user.tfa_secret = "JBSWY3DPEHPK3PXP"
    user.save(update_fields=["tfa_secret"])

    with connection.cursor() as cursor:
        cursor.execute("SELECT tfa_secret FROM accounts_user WHERE id = %s", [user.pk])
        row = cursor.fetchone()

    assert row is not None
    raw = row[0]
    assert raw != "JBSWY3DPEHPK3PXP"
    assert raw.startswith("gAAAA")  # Fernet ciphertext token marker.


@pytest.mark.django_db
def test_encrypted_text_field_empty_string_is_passthrough() -> None:
    user = User.objects.create_user(email="enc3@example.com", password="pw")
    # Default for tfa_secret is "" — should round-trip without invoking
    # Fernet (writing "" as the empty payload is intentional).
    assert user.tfa_secret == ""

    with connection.cursor() as cursor:
        cursor.execute("SELECT tfa_secret FROM accounts_user WHERE id = %s", [user.pk])
        row = cursor.fetchone()

    assert row is not None
    assert row[0] == ""
