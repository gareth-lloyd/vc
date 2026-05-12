from __future__ import annotations

from collections.abc import Iterator

import pytest
from django.contrib.contenttypes.models import ContentType

from accounts.models import User
from integrations.enums import SyncDirection, SyncProvider, SyncStatus
from integrations.models import SyncRecord
from integrations.signals import register_sync_target, unregister_sync_target


@pytest.fixture
def registered_user_sync() -> Iterator[None]:
    register_sync_target(
        User,
        providers=[SyncProvider.ZOHO_CRM.value],
        direction=SyncDirection.PUSH.value,
        fields=["email"],
    )
    yield
    unregister_sync_target(User)


@pytest.mark.django_db
def test_register_sync_target_creates_sync_record_on_save(
    registered_user_sync: None,
) -> None:
    user = User.objects.create_user(email="ada@example.com", password="secret")

    record = SyncRecord.objects.get(
        content_type=ContentType.objects.get_for_model(User),
        object_id=user.pk,
        provider=SyncProvider.ZOHO_CRM.value,
    )
    assert record.status == SyncStatus.PENDING
    assert record.direction == SyncDirection.PUSH


@pytest.mark.django_db
def test_register_sync_target_only_dirties_record_when_tracked_field_changes(
    registered_user_sync: None,
) -> None:
    user = User.objects.create_user(email="ada@example.com", password="secret")
    content_type = ContentType.objects.get_for_model(User)
    record = SyncRecord.objects.get(
        content_type=content_type,
        object_id=user.pk,
        provider=SyncProvider.ZOHO_CRM.value,
    )
    record.status = SyncStatus.IN_SYNC
    record.save(update_fields=["status", "updated_at"])

    # Changing an untracked field — `last_login_ip` is not in `fields=["email"]`.
    user.last_login_ip = "127.0.0.1"
    user.save()

    record.refresh_from_db()
    assert record.status == SyncStatus.IN_SYNC

    # Changing a tracked field flips the record back to PENDING.
    user.email = "ada-new@example.com"
    user.save()

    record.refresh_from_db()
    assert record.status == SyncStatus.PENDING


@pytest.mark.django_db
def test_unregister_sync_target_disconnects_signal() -> None:
    register_sync_target(
        User,
        providers=[SyncProvider.ZOHO_CRM.value],
        direction=SyncDirection.PUSH.value,
    )
    unregister_sync_target(User)

    user = User.objects.create_user(email="ada@example.com", password="secret")

    assert not SyncRecord.objects.filter(
        content_type=ContentType.objects.get_for_model(User),
        object_id=user.pk,
    ).exists()
