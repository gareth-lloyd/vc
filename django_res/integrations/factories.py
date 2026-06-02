"""factory-boy factories for the `integrations` app.

`OAuthCredentialFactory` defaults `is_active=False` because the partial-unique
constraint `unique_active_oauth_per_provider` allows only one active row per
provider — additive seed runs collide otherwise. Stages that want the
canonical active row should pass `is_active=True` explicitly.

`SyncRecordFactory` takes a `target` model instance via `target` kwarg; the
unique constraint `(content_type, object_id, provider)` means the same
(target, provider) pair cannot be created twice — so the seed stage handles
collision avoidance by varying the provider per call.
"""

from __future__ import annotations

from datetime import timedelta

import factory
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from factory.django import DjangoModelFactory

from core.factories import RUN_TOKEN
from integrations import models
from integrations.enums import (
    OAuthProvider,
    RunTriggeredBy,
    SyncDirection,
    SyncIssueKind,
    SyncIssueSeverity,
    SyncProvider,
    SyncRunStatus,
    SyncStatus,
)


class OAuthCredentialFactory(DjangoModelFactory):
    class Meta:
        model = models.OAuthCredential

    provider = OAuthProvider.ZOHO_CRM
    account_label = factory.Sequence(lambda n: f"account-{RUN_TOKEN}-{n}")
    access_token = "seed-access"
    refresh_token = "seed-refresh"
    token_type = "Bearer"
    expires_at = factory.LazyFunction(lambda: timezone.now() + timedelta(hours=1))
    scope = "ZohoCRM.modules.ALL"
    account_id = factory.Sequence(lambda n: f"zoho-{RUN_TOKEN}-{n}")
    # Default off so additive runs do not violate `unique_active_oauth_per_provider`.
    is_active = False


class SyncRunFactory(DjangoModelFactory):
    class Meta:
        model = models.SyncRun

    provider = SyncProvider.ZOHO_CRM
    direction = SyncDirection.PUSH
    started_at = factory.LazyFunction(timezone.now)
    finished_at = factory.LazyFunction(timezone.now)
    status = SyncRunStatus.SUCCEEDED
    records_processed = 10
    records_succeeded = 10
    records_failed = 0
    triggered_by = RunTriggeredBy.SCHEDULE


class SyncRecordFactory(DjangoModelFactory):
    """Generic-FK SyncRecord. Caller must supply `target` (a model instance);
    `content_type` and `object_id` are derived from it.
    """

    class Meta:
        model = models.SyncRecord
        exclude = ("target",)

    target = None  # required by caller
    content_type = factory.LazyAttribute(
        lambda o: ContentType.objects.get_for_model(o.target.__class__)
    )
    object_id = factory.LazyAttribute(lambda o: o.target.pk)
    provider = SyncProvider.ZOHO_CRM
    external_id = factory.Sequence(lambda n: f"ext-{RUN_TOKEN}-{n}")
    direction = SyncDirection.PUSH
    status = SyncStatus.IN_SYNC


class SyncIssueFactory(DjangoModelFactory):
    class Meta:
        model = models.SyncIssue

    run = factory.SubFactory(SyncRunFactory)
    record = None
    kind = SyncIssueKind.DRIFT
    severity = SyncIssueSeverity.WARNING
    local_state = factory.LazyFunction(dict)
    remote_state = factory.LazyFunction(dict)
    message = "Detected drift between local and remote."
