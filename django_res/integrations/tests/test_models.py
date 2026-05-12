from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError
from django.utils import timezone

from accounts.models import User
from integrations.enums import (
    OAuthProvider,
    SyncDirection,
    SyncProvider,
    SyncStatus,
)
from integrations.models import OAuthCredential, SyncRecord


@pytest.fixture
def user(db: None) -> User:
    return User.objects.create_user(email="ops@example.com", password="secret")


@pytest.mark.django_db
def test_sync_record_unique_per_target_provider(user: User) -> None:
    content_type = ContentType.objects.get_for_model(User)

    SyncRecord.objects.create(
        content_type=content_type,
        object_id=user.pk,
        provider=SyncProvider.ZOHO_CRM,
        direction=SyncDirection.PUSH,
    )

    with pytest.raises(IntegrityError):
        SyncRecord.objects.create(
            content_type=content_type,
            object_id=user.pk,
            provider=SyncProvider.ZOHO_CRM,
            direction=SyncDirection.PUSH,
        )


@pytest.mark.django_db
def test_sync_record_unique_external_id_when_present(user: User) -> None:
    other = User.objects.create_user(email="other@example.com", password="secret")
    content_type = ContentType.objects.get_for_model(User)

    SyncRecord.objects.create(
        content_type=content_type,
        object_id=user.pk,
        provider=SyncProvider.ZOHO_CRM,
        direction=SyncDirection.PUSH,
        external_id="zoho-123",
    )

    with pytest.raises(IntegrityError):
        SyncRecord.objects.create(
            content_type=content_type,
            object_id=other.pk,
            provider=SyncProvider.ZOHO_CRM,
            direction=SyncDirection.PUSH,
            external_id="zoho-123",
        )


@pytest.mark.django_db
def test_sync_record_blank_external_id_allows_duplicates(user: User) -> None:
    other = User.objects.create_user(email="other@example.com", password="secret")
    content_type = ContentType.objects.get_for_model(User)

    SyncRecord.objects.create(
        content_type=content_type,
        object_id=user.pk,
        provider=SyncProvider.ZOHO_CRM,
        direction=SyncDirection.PUSH,
        external_id="",
    )
    SyncRecord.objects.create(
        content_type=content_type,
        object_id=other.pk,
        provider=SyncProvider.ZOHO_CRM,
        direction=SyncDirection.PUSH,
        external_id="",
    )


@pytest.mark.django_db
def test_only_one_active_oauth_credential_per_provider() -> None:
    expires = timezone.now() + timedelta(hours=1)
    OAuthCredential.objects.create(
        provider=OAuthProvider.ZOHO_CRM,
        access_token="t1",
        refresh_token="r1",
        expires_at=expires,
        is_active=True,
    )

    with pytest.raises(IntegrityError):
        OAuthCredential.objects.create(
            provider=OAuthProvider.ZOHO_CRM,
            access_token="t2",
            refresh_token="r2",
            expires_at=expires,
            is_active=True,
        )


@pytest.mark.django_db
def test_oauth_credential_inactive_rows_allowed() -> None:
    expires = timezone.now() + timedelta(hours=1)
    OAuthCredential.objects.create(
        provider=OAuthProvider.ZOHO_CRM,
        access_token="t1",
        expires_at=expires,
        is_active=False,
    )
    OAuthCredential.objects.create(
        provider=OAuthProvider.ZOHO_CRM,
        access_token="t2",
        expires_at=expires,
        is_active=True,
    )


@pytest.mark.django_db
def test_oauth_credential_token_encryption_round_trip() -> None:
    expires = timezone.now() + timedelta(hours=1)
    credential = OAuthCredential.objects.create(
        provider=OAuthProvider.ZOHO_CRM,
        access_token="plaintext-access",
        refresh_token="plaintext-refresh",
        expires_at=expires,
    )

    # Raw DB column is ciphertext — bypass the field's from_db_value via raw SQL.
    from django.db import connection

    table = OAuthCredential._meta.db_table
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT access_token, refresh_token FROM {table} WHERE id = %s",
            [credential.pk],
        )
        raw_access, raw_refresh = cursor.fetchone()

    assert raw_access != "plaintext-access"
    assert raw_refresh != "plaintext-refresh"
    assert raw_access  # not empty

    # Refetched model decrypts back to plaintext.
    fetched = OAuthCredential.objects.get(pk=credential.pk)
    assert fetched.access_token == "plaintext-access"
    assert fetched.refresh_token == "plaintext-refresh"


@pytest.mark.django_db
def test_sync_status_defaults_to_pending(user: User) -> None:
    record = SyncRecord.objects.create(
        content_type=ContentType.objects.get_for_model(User),
        object_id=user.pk,
        provider=SyncProvider.ZOHO_CRM,
        direction=SyncDirection.PUSH,
    )
    assert record.status == SyncStatus.PENDING
