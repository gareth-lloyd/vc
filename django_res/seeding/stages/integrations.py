"""OAuth credentials + SyncRun / SyncRecord / SyncIssue rows.

Knob: `runs_per_channel` — runs per `SyncProvider`. Skipped when 0.

`OAuthCredential` has `unique_active_oauth_per_provider` (partial unique on
`is_active=True`). The very first per-provider credential is marked active;
additive reruns add fresh-but-inactive rows.

`SyncRecord` has `(content_type, object_id, provider)` unique. Each property
gets at most one record per provider per run — additive reruns rely on the
`IntegrityError` short-circuit, which the runner catches in the stage report.
"""

from __future__ import annotations

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from integrations.enums import (
    OAuthProvider,
    SyncDirection,
    SyncIssueKind,
    SyncIssueSeverity,
    SyncProvider,
    SyncRunStatus,
    SyncStatus,
)
from integrations.factories import (
    OAuthCredentialFactory,
    SyncIssueFactory,
    SyncRecordFactory,
    SyncRunFactory,
)
from integrations.models.oauth_credential import OAuthCredential
from seeding.context import SeedContext
from seeding.registry import Stage, register


def _ensure_oauth_credentials() -> int:
    """One active credential per provider. Additive runs keep the existing
    active row and append a fresh inactive sibling."""
    made = 0
    for provider in OAuthProvider:
        is_active = not OAuthCredential.objects.filter(provider=provider, is_active=True).exists()
        OAuthCredentialFactory(provider=provider, is_active=is_active)
        made += 1
    return made


def _make_records_for_run(ctx: SeedContext, provider: str) -> list[object]:
    """Create one SyncRecord per random property under `provider`. Skips on
    collision with the (content_type, object_id, provider) unique constraint,
    which fires on additive reruns of the same provider/property pair."""
    n_records = min(ctx.rng.randint(5, 15), len(ctx.properties))
    picked = ctx.rng.sample(ctx.properties, k=n_records)
    records: list[object] = []
    for prop in picked:
        try:
            with transaction.atomic():
                record = SyncRecordFactory(
                    target=prop,
                    provider=provider,
                    direction=SyncDirection.PUSH,
                    status=SyncStatus.IN_SYNC,
                )
            records.append(record)
        except IntegrityError:
            continue
    return records


def _run(ctx: SeedContext) -> int:
    if ctx.knobs.runs_per_channel <= 0:
        return 0
    if not ctx.properties:
        return 0
    made = _ensure_oauth_credentials()
    now = timezone.now()
    for provider in SyncProvider:
        for run_idx in range(ctx.knobs.runs_per_channel):
            started_at = now - timedelta(hours=run_idx * 6)
            status = SyncRunStatus.SUCCEEDED if run_idx % 3 != 0 else SyncRunStatus.PARTIAL
            run = SyncRunFactory(
                provider=provider,
                direction=SyncDirection.PUSH,
                started_at=started_at,
                finished_at=started_at + timedelta(minutes=5),
                status=status,
            )
            made += 1
            records = _make_records_for_run(ctx, provider)
            made += len(records)
            anchor_record = records[0] if records else None
            for severity, kind in (
                (SyncIssueSeverity.WARNING, SyncIssueKind.DRIFT),
                (SyncIssueSeverity.INFO, SyncIssueKind.VALIDATION),
            ):
                SyncIssueFactory(
                    run=run,
                    record=anchor_record,
                    severity=severity,
                    kind=kind,
                )
                made += 1
    return made


register(Stage(name="integrations", run=_run, depends_on=("properties",)))
