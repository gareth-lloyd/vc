"""Factory smoke tests for the integrations app."""

from __future__ import annotations

from typing import cast

import pytest

from integrations import factories, models
from properties.factories import PropertyFactory

pytestmark = pytest.mark.django_db


def test_oauth_credential_factory_defaults_inactive() -> None:
    c1 = cast(models.OAuthCredential, factories.OAuthCredentialFactory())
    c2 = cast(models.OAuthCredential, factories.OAuthCredentialFactory())
    # Default off so the partial-unique `unique_active_oauth_per_provider`
    # constraint allows additive runs to coexist.
    assert c1.is_active is False
    assert c2.is_active is False
    assert c1.pk != c2.pk


def test_sync_run_factory_persists() -> None:
    run = cast(models.SyncRun, factories.SyncRunFactory())
    assert run.pk is not None
    assert run.provider
    assert run.records_processed >= 0


def test_sync_record_factory_with_target() -> None:
    from typing import Any

    prop = cast(Any, PropertyFactory())
    record = cast(
        models.SyncRecord,
        factories.SyncRecordFactory(target=prop),
    )
    assert record.pk is not None
    assert record.object_id == prop.pk
    assert record.content_type.model == "property"


def test_sync_issue_factory_persists() -> None:
    issue = cast(models.SyncIssue, factories.SyncIssueFactory())
    assert issue.pk is not None
    assert issue.run_id is not None
