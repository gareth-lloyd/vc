# 11 · Integrations

Outbound integrations: Zoho CRM, the public WordPress site (Res API), Flywire payment gateway, and SMTP email delivery. Plus the orchestration that drives a full property data resync.

## Files

| File | Workflows |
|---|---|
| [`zoho-crm.md`](./zoho-crm.md) | OAuth refresh, push enquiry, push contact, push villa, push quotation/booking (custom modules: `VILLA_ENQUIRY`, `VILLA_MASTER_CONTACT`, `VILLLA_MASTER` `[TYPO]`, `VILLA_QUOTATIONS`, `VILLA_BOOKING`, `ARCHIVE_BOOKING`) |
| [`public-website-sync.md`](./public-website-sync.md) | All `WP_Sync_*` endpoints: countries, regions, features, collections, villas (full + variants), rooms, features, nearby, images, descriptions, alternative rentals, bookings, concierge, payment dues, Flywire checkout data; plus the `StartResSyncProcess` orchestration |
| [`flywire-gateway.md`](./flywire-gateway.md) | Charge (disabled), pre-auth (disabled), webhook receipt (cross-reference to `10-payment/`) |
| [`email-delivery.md`](./email-delivery.md) | SMTP send via global config, per-user SMTP send, VC internal send, template render + placeholders |

## Bird's-eye view

```
                        ┌────────────────────────────────┐
                        │      Res System (Django)       │
                        │                                │
                        │   ┌────────────────────────┐   │
   Flywire webhook ───▶ │   │  PaymentController      │   │
   (signed; not         │   │  + ResService           │   │
   verified[SECURITY])  │   └────────────────────────┘   │
                        │              │                 │
                        │              ▼                 │
                        │   ┌────────────────────────┐   │
                        │   │  Sync queue            │   │
                        │   │  (VillaSyncDetails)    │   │
                        │   └────────────────────────┘   │
                        └─────────────┬──────────────────┘
                                      │
            ┌────────────────────┬────┴────┬───────────────────┐
            ▼                    ▼         ▼                   ▼
       Zoho CRM         WordPress site   Flywire            SMTP server
       (custom modules) (WP_Sync_*)      (charge / preauth) (template emails)
```

## Cross-cutting concerns

- **Auth schemes diverge per integration**:
  - Zoho: OAuth refresh-token flow → `Zoho-oauthtoken` header
  - WordPress: Bearer token (per-site API key)
  - Flywire: `X-AUTHENTICATION-Key` header (base64-encoded API key)
  - SMTP: NetworkCredential (per-user or global)
- **Retry policy**:
  - Zoho OAuth refresh: 3 retries on timeout
  - All others: **no retry** captured in code
- **Idempotency**:
  - Zoho: identified by `RES_ID` (resync overwrites)
  - WordPress: local `SyncId` tracking prevents duplicate sends
  - Flywire / Email: none
- **Logging**: every integration writes a request/response file under `Utilities.WriteResLogFile(..., moduleName)` — these are operational logs, not structured events.
- **Hardcoded credentials** and **sandbox URLs** appear in source; covered in detail in the file for each integration.

## Open design questions for the Django redesign

- The data-model design (`../08-integrations.md`) plans a generic `integrations.SyncRecord` model with `GenericForeignKey` and a `SyncRecordStatus` enum. The redesign should:
  - Push every integration through Celery with retry + back-off
  - Persist webhook deliveries with idempotency
  - Verify HMAC signatures
  - Pull credentials from env / secret manager
- Replace the per-integration log-file pattern with structured events (Django logging + analytics emit).
- Multi-tenant WordPress (per-`SiteId` grouping) is real in the legacy code; decide whether to keep multi-target support.
