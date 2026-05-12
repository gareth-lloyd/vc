# 08 — Integrations

Pulls the integration/sync metadata (`ZohoId`, `SyncId`, `IsSync`, `OldVillaId`, `LastSyncedAt`) out of every domain model into a single `integrations` app. Domain models stay clean; sync state is observable in one place.

## File layout

```
integrations/
├── enums.py
├── models.py          # SyncRecord, SyncRun, SyncIssue
├── services.py        # SyncClient base, ZohoSyncClient, reconciliation services
├── tasks.py           # Celery: push, pull, reconcile, retry
└── signals.py         # auto-create SyncRecord on domain model save (opt-in)
```

## Models

### `SyncRecord(TimestampedModel)`
Generic FK to any synced domain model.
- `content_type` — FK ContentType
- `object_id` — PositiveBigInteger
- `target = GenericForeignKey("content_type", "object_id")`
- `provider` — TextChoices (`ZOHO_CRM`, `FLYWIRE`, `WORDPRESS_SITE`, `LEGACY_DOTNET`)
- `external_id` — CharField(blank=True, db_index=True)
- `external_url` — URLField(blank=True)  # admin convenience
- `direction` — TextChoices (`PUSH`, `PULL`, `BIDIRECTIONAL`)
- `status` — TextChoices (`PENDING`, `IN_SYNC`, `DRIFT`, `ERROR`, `DISABLED`)
- `last_pushed_at` — DateTimeField(null=True, blank=True)
- `last_pulled_at` — DateTimeField(null=True, blank=True)
- `last_drift_at` — DateTimeField(null=True, blank=True)
- `local_fingerprint` — CharField(blank=True)  # hash of local fields covered by sync
- `remote_fingerprint` — CharField(blank=True)
- `error_message` — TextField(blank=True)
- `retry_count` — PositiveSmallInteger(default=0)

Constraints:
- `UniqueConstraint(content_type, object_id, provider)` — one record per (target, provider).
- `UniqueConstraint(provider, external_id, condition=Q(external_id__gt=""))` — provider-side id is unique per provider.

Indexes: `(provider, status)`, `(content_type, object_id)`, `external_id`.

### `SyncRun(TimestampedModel)`
Audit of a sync job execution.
- `provider` — TextChoices
- `direction` — TextChoices
- `started_at`, `finished_at` — DateTimeField
- `status` — TextChoices (`RUNNING`, `SUCCEEDED`, `FAILED`, `PARTIAL`)
- `records_processed`, `records_succeeded`, `records_failed` — PositiveIntegerField
- `triggered_by` — TextChoices (`SCHEDULE`, `MANUAL`, `SIGNAL`)
- `actor` — FK User SET_NULL, null=True
- `error_summary` — TextField(blank=True)

### `SyncIssue(TimestampedModel)`
A specific problem during a run (drift, conflict, error). Surfaced to ops.
- `run` — FK SyncRun CASCADE
- `record` — FK SyncRecord PROTECT, null=True
- `kind` — TextChoices (`DRIFT`, `CONFLICT`, `MISSING_REMOTE`, `MISSING_LOCAL`, `VALIDATION`, `TRANSIENT_ERROR`)
- `severity` — TextChoices (`INFO`, `WARNING`, `ERROR`)
- `local_state` — JSONField(default=dict)
- `remote_state` — JSONField(default=dict)
- `message` — TextField(blank=True)
- `resolved_at` — DateTimeField(null=True, blank=True)
- `resolved_by` — FK User SET_NULL, null=True
- `resolution` — TextField(blank=True)

Indexes: `(severity, resolved_at)`, `(kind, resolved_at)`.

## Services

### `SyncClient` base
Stateless. Each provider has a subclass that knows how to push, pull, and reconcile.

```python
class SyncClient:
    provider: str

    def push(self, instance) -> SyncRecord: ...
    def pull(self, external_id) -> dict: ...
    def reconcile(self, instance) -> SyncIssue | None: ...
    def fingerprint(self, payload: dict) -> str: ...
```

### `ZohoSyncClient`
Pushes `Property`, `Quotation`, `Booking`, `Guest` to Zoho CRM. Pulls limited fields back (mostly status changes from CRM-side activity). Reconciliation compares fingerprints daily.

### Reconciliation flow

Nightly Celery beat task per provider:
1. Open a `SyncRun(status=RUNNING)`.
2. For each `SyncRecord` for the provider with `status != DISABLED`:
   - Fetch remote.
   - Compare `remote_fingerprint` to current remote.
   - If drift: write a `SyncIssue(kind=DRIFT, severity=WARNING)`, set `record.status=DRIFT`, do not auto-resolve (drift may be legitimate CRM-side edit).
   - If missing on remote: `SyncIssue(kind=MISSING_REMOTE)`, optionally re-push.
   - On transient error: `SyncIssue(kind=TRANSIENT_ERROR, severity=INFO)`, increment retry_count, leave `status=IN_SYNC` if a previous push was successful.
3. Close the `SyncRun(status=SUCCEEDED/PARTIAL/FAILED)`.

## Auto-create on domain save (opt-in)

Each domain app's `apps.py` `ready()` registers `post_save` handlers via a small declarative API:

```python
# in properties.apps.PropertiesConfig.ready()
from integrations.signals import register_sync_target

register_sync_target(Property, providers=["ZOHO_CRM"], direction="PUSH")
register_sync_target(Booking, providers=["ZOHO_CRM"], direction="BIDIRECTIONAL")
```

The handler:
- On create: creates a `SyncRecord(status=PENDING)`.
- On update: bumps `SyncRecord.status=PENDING` (signals push needed) **only if fields covered by the sync changed** (the registration declares which fields matter; otherwise we'd thrash on irrelevant edits).
- A Celery task `push_pending` runs every few minutes, batching pushes.

## Why generic over per-model fields

The legacy approach scattered `ZohoId`, `SyncId`, `LastSyncedAt`, `IsSync` across every table. Adding a new integration meant a schema migration on every domain table.

With `SyncRecord`:
- Adding a new provider = inserting new SyncRecord rows, no schema migration.
- Removing a provider = updating SyncRecord rows.
- Ops can answer "what's in drift right now?" with one query.
- Domain models stay focused on the domain.

Cost: a tiny indirection cost when admin wants to see "what's the Zoho id for this booking?" — easy convenience method on the model:
```python
def zoho_id(self) -> str | None:
    try:
        return self.sync_records.get(provider="ZOHO_CRM").external_id
    except SyncRecord.DoesNotExist:
        return None
```

## Dropped from legacy

- `ZohoId` columns on every model.
- `SyncId`, `IsSync`, `IsSynced` booleans everywhere.
- `OldVillaId`, `OldId` columns — replaced by `legacy_id` (a single per-model field for free-form legacy reference, plus `SyncRecord` for the structured legacy-system sync if needed).
- `VillaCodeSentHistory`, `VillaEmailLinkLog` — not really integration concerns; they belong in a future `comms` app or are dropped.

## Out of scope

- WordPress site sync details (the legacy `VillaSite` table) — the model fits this framework but the protocol specifics are TBD.
- Channel manager integrations (Booking.com, Vrbo, Airbnb) — none in the legacy system; future scope.
