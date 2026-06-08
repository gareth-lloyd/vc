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
- `provider_instance` — CharField(max_length=64, blank=True, db_index=True)  # which tenant/site within `provider`; e.g. WordPress `SiteId` ("1", "2", …). Empty for single-tenant providers (Zoho, Flywire today).
- `external_id` — CharField(blank=True, db_index=True)
- `external_url` — URLField(blank=True)  # admin convenience; also the canonical public URL (e.g. WordPress booking page slug returned by `Import_Booking`)
- `direction` — TextChoices (`PUSH`, `PULL`, `BIDIRECTIONAL`)
- `status` — TextChoices (`PENDING`, `IN_SYNC`, `DRIFT`, `ERROR`, `DISABLED`)
- `last_pushed_at` — DateTimeField(null=True, blank=True)
- `last_pulled_at` — DateTimeField(null=True, blank=True)
- `last_drift_at` — DateTimeField(null=True, blank=True)
- `local_fingerprint` — CharField(blank=True)  # hash of local fields covered by sync
- `remote_fingerprint` — CharField(blank=True)
- `error_message` — TextField(blank=True)
- `retry_count` — PositiveSmallInteger(default=0)
- `meta` — JSONField(default=dict)  # provider-specific extras (e.g. WP `PostId` when the slug is the `external_id`; Zoho `module` name)

Constraints:
- `UniqueConstraint(content_type, object_id, provider, provider_instance)` — one record per (target, provider, instance).
- `UniqueConstraint(provider, provider_instance, external_id, condition=Q(external_id__gt=""))` — provider-side id is unique within a provider+instance.

Indexes: `(provider, provider_instance, status)`, `(content_type, object_id)`, `external_id`.

> **Why `provider_instance`?** WordPress is multi-tenant in the legacy system (`VillaSyncDetail.SiteId` distinguishes which public site a given villa/booking was published to, each with its own post-id and slug). A single `provider=WORDPRESS_SITE` row per villa cannot represent the fan-out. `provider_instance` carries the site identifier so each (villa, site) pair gets its own row, matching the legacy `(SiteId, ModuleId, ModulePrimaryId)` triple. Zoho today is single-tenant, so its rows leave `provider_instance` empty — but the field future-proofs the model if a second Zoho org is ever introduced.

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

Enquiries also carry CRM tags on push: `Enquiry.lead_status` (the `HOT`/`WARM`/`COLD`/`DEAD` TextChoices added in `05-reservations.md`) is pushed to Zoho as a lead tag, alongside the existing loss reason captured on the `LOST` `EnquiryEvent`. See `05-reservations.md`.

> **Open question — lead-management primacy.** The sales team may move inquiry management from Res into Zoho. Two shapes are on the table: (a) **Res-primary** (current; Zoho mirrors via this client), or (b) **Zoho-primary for leads** (Res consumes via inbound pull, with the Zoho-side `Enquiry` module as source of truth). MVP keeps Res-primary; flipping primacy is a v2 decision driven by the sales-team interview after the 2026-05-26 scoping session. Tracked in `10-decisions.md` "Open follow-ups".

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

## Migrating legacy external IDs — continuity for Zoho and WordPress

The single most important migration step for the integrations app is **preserving the external IDs already issued by Zoho and WordPress against legacy rows**. These IDs are the routing keys for every subsequent update; if we drop them, the first post-cutover sync silently creates duplicates on the remote side and orphans the originals.

### Where the legacy IDs live

| Legacy column | Local entity | Maps to | Notes |
|---|---|---|---|
| `VillaMaster.ZohoId` | Property | `SyncRecord(provider=ZOHO_CRM, external_id=ZohoId)` | Zoho module `VILLLA_MASTER` (legacy typo, see workflow doc). |
| `VillaContact.ZohoId` | Contact | `SyncRecord(provider=ZOHO_CRM, external_id=ZohoId)` | Zoho module `VILLA_MASTER_CONTACT`. |
| `VillaEnquire.ZohoId` | Enquiry | `SyncRecord(provider=ZOHO_CRM, external_id=ZohoId)` | Zoho module `VILLA_ENQUIRY`. |
| `VillaQuotationMaster.ZohoId` | Quotation | `SyncRecord(provider=ZOHO_CRM, external_id=ZohoId)` | Zoho module `VILLA_QUOTATIONS`. |
| `VillaBooking.ZohoId` | Booking | `SyncRecord(provider=ZOHO_CRM, external_id=ZohoId)` | Zoho module `VILLA_BOOKING` / `ARCHIVE_BOOKING`. |
| `VillaBooking.BookingUrl` | Booking | `SyncRecord(provider=WORDPRESS_SITE, provider_instance=<SiteId>, external_url=BookingUrl)` | The legacy code stores only the URL, not the WP `PostId`; treat the URL as the external identifier for the WP side. If the WP `PostId` is recoverable from logs or a `VillaSyncDetail` row, populate `meta["wp_post_id"]`. |
| `VIllaConcierges.Slug` | Concierge service | `SyncRecord(provider=WORDPRESS_SITE, provider_instance=<SiteId>, external_url=Slug)` | Same shape as `BookingUrl`. |
| `VillaSyncDetail` (whole table) | Any module | One `SyncRecord` per row | The normalised source of truth for WP sync state. See below. |

`VillaSyncDetail` is the per-site sync table in legacy. Each row carries:
- `SiteId` → `SyncRecord.provider_instance`
- `ModuleId` → resolves to a Django `ContentType` (see mapping table in `data_migration/loaders/integrations.py`)
- `ModulePrimaryId` → `SyncRecord.object_id` (after the per-module legacy-id lookup; e.g. `VillaMaster.Id → Property.id`)
- `SyncId` → WordPress post id; store as `SyncRecord.external_id` (string-cast)
- `VillaUrl` → `SyncRecord.external_url`
- `Process` → free-form legacy status string; if useful, stash in `meta["legacy_process"]`

### Migration loader

Add `data_migration/loaders/integrations.py` with two loaders, both idempotent upserts:

1. **`SyncRecordZohoLoader`** — sweeps the legacy tables above, and for any row with a non-blank `ZohoId` emits an upsert:
   ```python
   SyncRecord.objects.update_or_create(
       content_type=ContentType.objects.get_for_model(Property),
       object_id=property_pk,
       provider="ZOHO_CRM",
       provider_instance="",
       defaults=dict(
           external_id=legacy_zoho_id,
           direction="PUSH",
           status="IN_SYNC",
           last_pushed_at=legacy_updated_at or legacy_created_at,
       ),
   )
   ```
   Keyed on `(content_type, object_id, provider, provider_instance)` so re-runs are safe (mirrors the existing loader convention — see `CUTOVER.md`).

2. **`SyncRecordWordPressLoader`** — iterates `VillaSyncDetail` directly. For each row, resolve the local target via the module-id → model map, then upsert a `SyncRecord` with `provider="WORDPRESS_SITE"`, `provider_instance=str(SiteId)`. Backfill `BookingUrl` and `VIllaConcierges.Slug` separately for rows where `VillaSyncDetail` has no entry but a URL exists on the source row (defensive — legacy code paths don't always write to `VillaSyncDetail`).

Register both in `data_migration/registry.py` **after** the corresponding domain loaders (Property, Contact, Enquiry, Quotation, Booking) so the target rows exist when `SyncRecord` rows are written.

### Sanity check during reconcile

Extend `reconcile_legacy` to report:
- Count of legacy rows with a non-blank external id (`ZohoId`, `BookingUrl`, `Slug`) per source table.
- Count of `SyncRecord` rows created per `(provider, provider_instance)` pair.
- Any row with a legacy external id but no matching `SyncRecord` is a **blocker** — duplicates will be issued on first sync if it goes uncaught.

### Why this matters at cutover

- **Zoho push routes on `Zoho_ID`.** `PushZohoEnqueireAsync` and friends put the legacy `Zoho_ID` in the payload's `Enquiry`/`Villa`/`Booking` sub-object. The Zoho-side Deluge function (`fn_enquirypath`, `fn_quotepath`, `fn_bookingpath`) decides INSERT vs UPDATE on whether that id is present and recognised. A missing id ⇒ new Zoho record. With ~years of CRM activity attached to existing records (notes, tasks, emails, deal stage), losing the link is operationally serious.
- **WordPress `Import_Booking` and `WP_Sync_Villa` are not idempotent on local content.** The WP side allocates a new post on every call without a matching post id; the canonical booking-confirmation URL changes; previously-emailed guest links 404.
- **Multi-site fan-out doubles the surface area.** Each `(villa, site)` pair has its own slug and post id. Migration must preserve all of them, not just the most-recently-touched one.

### Stop-the-bleeding posture during cutover

Until the external-id migration is verified clean (the reconcile step above passes), the post-deploy push tasks must be **disabled** (set `SyncRecord.status=DISABLED` for the relevant providers, or pause the Celery beat schedule). Re-enable only after the operator runs a dry-run reconciliation against Zoho and a sample WP site and confirms no orphans. This is the most likely place to manufacture a hard-to-recover production mess; treat it as the critical-path gate.

## Inbound: WordPress → Django

The public villacollective.com WordPress site originates a small number of writes against the Res API (guest checkout submission, payment-status callbacks from the WP-hosted Flywire return page, enquiry capture from the marketing forms). Legacy handled this via the `WordPressApi/*` controllers with no documented auth story (see `[SECURITY]` notes in `workflows/11-integrations/flywire-gateway.md` and `workflows/10-payment/checkout-flow.md`). For the rebuild we standardise on a single, boring pattern.

### Auth: DRF `TokenAuthentication` + dedicated service user

- One Django user per WordPress site (e.g. `wordpress-publisher`). Created via data migration with `is_staff=False`, `is_active=True`, and an unusable password (`set_unusable_password()`) — the token is the only credential. No new `Role` enum value, no `INTEGRATION_SERVICE` flag; the user is identified by username, configured in `settings.WORDPRESS_SERVICE_USERNAME`.
- One `authtoken.Token` per service user. Token is generated once and copied into the WordPress side; never stored in Django plaintext outside the `authtoken` table.
- WordPress stores the token in `wp-config.php` as a `define('VC_RES_API_TOKEN', '…')` constant — **not** in the WP database, **not** committed to the plugin source. Reason: `wp-config.php` is the established convention for secrets in WP and is excluded from plugin distributions, theme exports, and most backup tooling. Storing in `wp_options` would surface the token to any WP plugin with DB read access.
- WordPress calls the API with `Authorization: Token <value>` over HTTPS only. HTTP requests are rejected at the proxy.
- Token rotation is in-place: generate a new `authtoken.Token` for the service user, update `wp-config.php`, then delete the old token row. No code change, no schema change.

We deliberately avoid:
- **JWT** — refresh/expiry machinery is wasted for a server-to-server caller with one credential.
- **OAuth2** — there is no user-delegated authorisation happening; WP is the client, not a delegated identity.
- **HMAC-signed requests** — strictly more secure against token leakage but materially harder to operate (clock skew, canonical-request bugs, shared-secret rotation). Revisit only if we discover the token cannot be kept secret on the WP host.
- **WordPress Application Passwords** — those auth the *other* direction (Django → WP), which is the outbound sync covered elsewhere in this doc.

### Endpoint surface

Inbound WP endpoints live under a single URL prefix `/api/wordpress/*` so the permission class, throttle, and `IP allowlist` middleware can be applied to the whole subtree:

- `POST /api/wordpress/enquiries/` — marketing-form enquiry capture. **Stays inbound from WordPress** — WP remains the public lead-capture source.
- ~~`POST /api/wordpress/checkout/`~~ — guest checkout submission (legacy `SaveCheckoutInfo`). **Moves first-party in Milestone 1.** The guest checkout journey is now hosted by the React SPA (`portal.villacollective.com/booking?ref=…`) and submits directly to the Django API, not via WordPress. See `11-milestones.md`, `workflows/10-payment/checkout-flow.md`, and `10-decisions.md` "Guest booking/checkout journey hosted in the SPA".
- ~~`POST /api/wordpress/payments/return/`~~ — Flywire return-page callback (legacy `TokenisePaymentStatus`). **Moves first-party in Milestone 1** — the SPA hosts the Flywire return page and the callback lands directly on the Django API.
- ~~`POST /api/wordpress/payments/webhook/`~~ — Flywire server-to-server webhook (legacy `PaymentStatusWebHook`). **Moves direct-to-Django in Milestone 1.** This resolves the open question in `workflows/11-integrations/flywire-gateway.md` (WP-proxied vs. direct-to-Django) toward **direct-to-Django** for the rebuild: Flywire posts straight to the Django API rather than being proxied through the WP site.

> **First-party checkout (M1) — honest scope note.** Per `10-decisions.md` "Guest booking/checkout journey hosted in the SPA", the checkout / payment-return / payment-webhook endpoints above leave the inbound WordPress surface in Milestone 1. The security win is real: this removes the legacy unauthenticated `WordPressApi/*` checkout surface entirely. But be honest — this is **not** a net simplification. It *adds* first-party Flywire return-page hosting and first-party return/webhook handling to M1 (work that is currently WP-proxied), in exchange for owning the journey end-to-end. This is scoped narrowly to the checkout page; the broader post-booking guest portal stays deferred. The marketing-form enquiry capture (`POST /api/wordpress/enquiries/`) is unaffected and remains inbound from WordPress.

Each endpoint:
- Uses a focused DRF serializer that accepts **only** the fields it consumes. No `extra` dict, no passthrough.
- Has a `permission_classes = [IsWordPressServiceUser]` that checks `request.user.username == settings.WORDPRESS_SERVICE_USERNAME`. Defence in depth against a leaked token from any other user being repurposed against this surface — the username pin means only the WP service user's token is accepted on this URL subtree, even if another valid token is presented.
- Is throttled via DRF `ScopedRateThrottle` (`scope = "wordpress_inbound"`); the rate is set per-endpoint in settings.
- Logs every call to `AuditLog` with `actor` = the service user, `action` = the endpoint, and the request payload (with PII fields hashed per `00-conventions.md`).

### Idempotency

Every WP-originated mutation carries a client-supplied idempotency key derived from a stable WordPress identifier (post id, form submission id, Flywire reference). The endpoint:
1. Looks up `IntegrationInboundCall(provider=WORDPRESS_SITE, idempotency_key=…)` (a small append-only table — `provider`, `idempotency_key`, `response_status`, `response_body_hash`, `created_at`, unique on `(provider, idempotency_key)`).
2. If present: returns the recorded response unchanged. Retries don't double-write.
3. If absent: processes the request inside a transaction, writes the row, returns.

This handles WP-side retry storms (cron-driven `wp_remote_post` will re-fire on plugin restart) without per-endpoint dedupe logic.

### Hardening that's cheap to add later

- **IP allowlist** at the proxy / DRF middleware if the WP host has a stable egress IP. Implement when the host's egress is pinned; skip until then to avoid blocking legitimate traffic during host migrations.
- **Token expiry**: replace `authtoken.Token` with `knox.AuthToken` only if/when we want time-bounded tokens. Default `authtoken` rows are fine for v1.
- **Per-endpoint scopes**: if we grow more inbound consumers, swap the single-token model for a `ServiceCredential(scopes=…)` row referenced by the permission class. Out of scope for v1 — one consumer, one token.

### What this replaces in legacy

- The unauthenticated `WordPressApi/*` controllers.
- The implicit "trust because internal network" posture.
- The ad-hoc `[SECURITY]` flags in `workflows/11-integrations/flywire-gateway.md` and `workflows/10-payment/*.md` for inbound verification: token-auth + idempotency + AuditLog is the answer.

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

- **Outbound** WordPress sync details (Django → WP `WP_Sync_*` push protocol, multi-`SiteId` fan-out, response shapes) — the `SyncRecord(provider=WORDPRESS_SITE)` framework holds the state, but the wire protocol is still being captured in `workflows/11-integrations/public-website-sync.md`. The **inbound** direction (WP → Django) is fully defined above. **Rate/pricing data is never pushed to WordPress** — it is internal-only and stays within the Res system; the outbound sync covers villa content (descriptions, imagery, slugs), not rates.
- **iCal feed ingest** from per-villa public calendars. Lands as a new `SyncProvider.ICAL` value on `SyncRecord` (reusing its `external_id` field as the per-feed idempotency key on the iCal `UID`) plus a poller writing `BookingHold(reason=OWNER_BLOCK, …)` rows. High-value v2 force-multiplier, not in MVP. Full spec, verified assumptions, and postponed decisions (incl. the secret-URL hazard): **`todo/gap-011-ical-feed-ingest.md`**.
- Channel manager integrations (Booking.com, Vrbo, Airbnb) — none in the legacy system; future scope.
