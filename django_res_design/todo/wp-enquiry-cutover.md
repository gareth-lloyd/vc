# WP enquiry intake — cutover runbook (fork C)

Status: **backend ready, awaiting WP-side change + cutover.** The Django
receiver for the WordPress enquiry form is live on `main`
(`POST /api/wordpress/enquiries`); this doc is the handoff to whoever edits
the WordPress plugin, plus the cutover checklist.

## What the WP site must send

- **URL:** `POST https://<django-host>/api/wordpress/enquiries`
  — no trailing slash (a trailing slash 404s; APPEND_SLASH cannot redirect a
  POST). JSON body, `Content-Type: application/json`.
- **Auth:** `Authorization: Token <VC_RES_API_TOKEN>` — DRF TokenAuthentication
  with a dedicated non-staff service user (`08-integrations.md` §"Inbound:
  WordPress → Django"). This replaces the legacy `X-API-Key` header.
  - Mint the token per environment with `./manage.py bootstrap_wordpress_user`
    (idempotent; `--rotate` to replace a leaked token).
  - Store it in `wp-config.php` as `define('VC_RES_API_TOKEN', '…')` — never
    in the WP database, never committed.
  - **Never reuse the legacy credentials** (`130d0022-…`, `E5FE4-…`, the
    `WP_Token` bearer) — all three are burned: committed to the repo and
    embedded in Postman collections.
- **Body:** the existing payload, unchanged. The serializer accepts the real
  wire shape verbatim (verified against 201 stored submissions in
  `ResSystem/vc_wp_1.sql`): `FirstName`, `LastName`, `Email`, `CountryCode`,
  `ContactNo`, `Properties` (string id, `"0"` = none), `RegionIds` (list of
  string ids, `"0"` = none), `FromDate`/`ToDate` (ISO dates),
  `EnquireDateType` + `EnquireDateTypeString` ("Specific dates" / "+/- 3
  days" / "Flexible" — the string wins), `CountryIds` (CSV), `MinBed`,
  `MaxBed`, `Adults`, `Children` (string ints fine), `Notes`, `referral`,
  `UserFeedback`, `other_text`, `IsSignUp`. The `.NET` DTO / Postman variants
  (`PropertyId`, `CountryId`, `Countries`, `Regions`) are also tolerated.
  Unknown keys are ignored (ASP.NET behaviour preserved).
- **Response:** `201 {"reference": "E…"}` (not the legacy
  `{Status, Message, Data, …}` envelope — the plugin must not parse for
  `"Enquire send successfully!."`). Retried duplicates replay the same 201.
  `400` = malformed field types; `401/403` = auth; `429` = throttled.
- **TLS:** `wp_remote_post` must NOT set `'sslverify' => false`. Check for
  this when the plugin source arrives.

## Smoke test (staging)

```bash
TOKEN=$(cd django_res && uv run python manage.py bootstrap_wordpress_user | grep -o 'Token.*: .*' | awk '{print $NF}')
curl -sS -X POST https://<staging-host>/api/wordpress/enquiries \
  -H "Authorization: Token $TOKEN" -H 'Content-Type: application/json' \
  -d '{"FirstName":"Smoke","Email":"smoke@example.com","Properties":"0","RegionIds":["0"],"EnquireDateTypeString":"Specific dates","FromDate":"2027-05-01","ToDate":"2027-05-08","Adults":"2","IsSignUp":false}'
# → 201 {"reference":"E…"}; repeat within the hour → same reference, no dup.
```

## Cutover checklist

1. WP developer updates the plugin: point the enquiry post at the new URL,
   send `Authorization: Token`, read the 201 envelope. (Plugin/theme source
   requested 2026-07-26 — villa-enquiry-manager, villacollective theme,
   mu-plugins, other custom plugins.)
2. `./manage.py bootstrap_wordpress_user` on production; copy the token to
   `wp-config.php` (secure channel).
3. Ensure `ZOHO_FLOW_WEBHOOK_ENQUIRY` is set in the Django environment if
   WP-originated enquiries should push to Zoho (empty = silently disabled).
4. **Gate:** one real end-to-end submission from the WP staging/live form
   against Django staging before flipping production. (The wire *shape* is
   already verified from `vc_wp_1.sql`; this confirms the plugin's headers +
   TLS behaviour, which the DB dump cannot show.)
5. Flip the plugin's target URL on production. Watch
   `reservations.enquiry.wordpress_intake_created` /
   `integrations.inbound_call.replayed` logs and the enquiry list.
6. Legacy receiver (`vc2.mojodev.co.uk`) keeps running untouched until the
   WP site stops posting to it; no dual-write window is needed (the form
   posts to exactly one target).

## Operational notes

- **Idempotency:** the payload carries no client key, so the server derives
  one — SHA-256 of the validated payload + a one-hour UTC bucket
  (`reservations/services/wordpress_intake.derive_idempotency_key`). Retry
  storms dedupe via the `IntegrationInboundCall` ledger; a retry pair
  straddling the top of the hour can double-write (accepted — retries are
  seconds apart). A genuine identical re-enquiry in a later hour is a new
  lead.
- **Throttle:** `wordpress_inbound` = 60/min, but no CACHES backend is
  configured so DRF throttling uses per-process LocMemCache — the effective
  ceiling is 60/min × worker count. Fine for a lead form; revisit if a real
  cache lands.
- **401s are not rate-limited** (throttling runs after auth in DRF).
  Accepted: 40-hex token space makes guessing impractical, and an anon
  throttle would hand attackers a DoS lever over legitimate traffic.
- **Audit trail:** every handled call writes an AuditLog row targeting the
  `IntegrationInboundCall` ledger row (actor = service user); the Enquiry
  create also emits the standard tracked-model diff row. Auth-rejected calls
  appear in request logs only.
- **Deliberate spec deviations** (erratum banners added to
  `08-integrations.md`): pin by email not username (`WORDPRESS_SERVICE_EMAIL`
  — `accounts.User` has no username column); the ledger stores the full
  `response_body`, not only a hash.

## Deferred (unchanged from the plan)

Customer confirmation email (needs comms template + copy sign-off); CF7
"contact us" forms; server-side reCAPTCHA; Person match-or-create by email;
WP outbound sync/backfill; any WP PHP changes beyond this handoff spec.
