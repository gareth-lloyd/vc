# 08 — Integrations

Pulls the integration/sync metadata (`ZohoId`, `SyncId`, `IsSync`, `OldVillaId`, `LastSyncedAt`) out of every domain model into a single `integrations` app. Domain models stay clean; sync state is observable in one place.

## File layout

```
integrations/
├── enums.py
├── models.py          # SyncRecord, SyncRun, SyncIssue, OAuthCredential
├── services.py        # SyncClient base, ZohoSyncClient, OAuthService, reconciliation services
├── tasks.py           # Celery: push, pull, reconcile, retry, refresh_oauth_tokens
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

### `OAuthCredential(AuditedModel)`

Token storage for OAuth-based integrations. Today only Zoho uses this; the model is provider-agnostic so future OAuth integrations (Mailchimp, HubSpot, etc.) add a `provider` enum value rather than a new table. See reconciliation issue #42.

- `provider` — TextChoices (`ZOHO_CRM`, …) — extensible; reuses the same string values as `SyncRecord.provider` where they overlap
- `account_label` — CharField(blank=True)  # operator-facing label ("Zoho CRM — sales@villacollective.com"); makes the admin row identifiable when multiple accounts/regions exist
- `access_token` — TextField  # encrypted at rest (Fernet wrap, same pattern as `User.tfa_secret` / `SmtpProfile`)
- `refresh_token` — TextField(blank=True)  # encrypted at rest; blank if the provider does not issue one
- `token_type` — CharField(max_length=32, default="Bearer")
- `expires_at` — DateTimeField  # access-token expiry; the refresh task fires when `now() + 5min >= expires_at`
- `scope` — CharField(blank=True)  # space-separated scopes granted at consent
- `account_id` — CharField(blank=True)  # provider-side account/org id (Zoho returns `api_domain` + `accounts_server` — store both via `meta`)
- `connected_by` — FK User SET_NULL, null=True, related_name="oauth_connections"  # the staff user who completed the `:connect` flow
- `connected_at` — DateTimeField(default=now)
- `disconnected_at` — DateTimeField(null=True, blank=True)  # set when `:disconnect` revokes; row is kept for audit until cleaned up manually
- `is_active` — BooleanField(default=True)  # `False` after `:disconnect` or after a refresh-token revocation by the provider
- `meta` — JSONField(default=dict)  # provider-specific blob (Zoho `api_domain`, `accounts_server`, etc.)

Constraints:
- `UniqueConstraint(provider, condition=Q(is_active=True), name="unique_active_oauth_per_provider")` — exactly one active credential per provider at a time. `:connect` while one exists transitions the existing row to `is_active=False` and writes a new active row; the old row stays for audit.

Indexes: `(provider, is_active)`, `(expires_at)` (used by the refresh-token Celery task).

**Encryption**: `access_token` and `refresh_token` use app-layer Fernet encryption (the same pattern used by `User.tfa_secret` and `comms.SmtpProfile`). Keys are read from `settings.FERNET_KEYS` (rotated via a key list, oldest-first decrypt, newest-first encrypt). Tokens are never logged; admin views mask them with `"***"`. Sensitive-field edits flow into `AuditLog` (per `00-conventions.md`).

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

Auth: reads the active `OAuthCredential(provider=ZOHO_CRM, is_active=True)` row via `OAuthService.get_access_token("ZOHO_CRM")` on every call. If the access token is within 5 minutes of expiry, the service refreshes it inline against the Zoho `/oauth/v2/token` endpoint (grant_type=refresh_token), writes the new `access_token` + `expires_at` to the row, and returns the fresh token. If no active credential exists, the client raises `OAuthNotConnectedError` and the calling Celery task records a `SyncIssue(kind=VALIDATION, severity=ERROR, message="Zoho not connected — operator must run /zoho:connect")`.

### `OAuthService`

OAuth-flow orchestration. Backs the API surface `/zoho:connect` / `/zoho:disconnect` (§2.27); see reconciliation issue #42.

```python
class OAuthService:
    def begin(self, provider: str, *, actor: User) -> str:
        """Return the provider's authorization-code URL.

        Generates a CSRF state token, persists it on a short-lived
        cache entry keyed by user, and returns the URL the browser
        should visit. The redirect-back endpoint posts the code +
        state back here via `complete()`.
        """

    def complete(self, provider: str, code: str, state: str, *, actor: User) -> OAuthCredential:
        """Exchange the authorization code for an access/refresh token pair.

        Validates `state` against the cache, calls the provider's token
        endpoint, transitions any existing active credential for this
        provider to `is_active=False`, writes a new row with the encrypted
        tokens, and returns it.
        """

    def disconnect(self, provider: str, *, actor: User) -> None:
        """Revoke and deactivate the active credential.

        Calls the provider's token-revocation endpoint (best-effort),
        sets `is_active=False` and `disconnected_at=now()` on the row,
        and writes an AuditLog entry.
        """

    def get_access_token(self, provider: str) -> str:
        """Return a valid access token, refreshing inline if near expiry.

        Used by all SyncClient subclasses. The refresh is wrapped in a
        Postgres advisory lock keyed on `(provider, credential_id)` so
        concurrent calls do not double-refresh.
        """
```

A `refresh_oauth_tokens` Celery beat task (hourly) pre-emptively refreshes any active credential whose `expires_at` is within the next hour, so the synchronous-refresh fallback in `get_access_token` is rarely exercised.

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
