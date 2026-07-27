# WP enquiry intake — cutover runbook (fork C)

Status: **backend ready, awaiting WP-side change + cutover.** The Django
receiver for the WordPress enquiry form is live on `main`
(`POST /api/wordpress/enquiries`); this doc is the handoff to whoever edits
the WordPress theme, plus the cutover checklist.

> **✅ WP source verified (2026-07-27)** — theme + plugins received
> (`ResSystem/wetransfer_remaining-plugins-zip_2026-07-27_1000/`). The sender
> is the **`villacollective` theme**, not the `villa-enquiry-manager` plugin
> (that plugin only stores submissions in a local `wp_villa_enquiries` table
> and renders an admin list — it never posts anywhere).
> See "As-built WP sender" below; the required WP change is now spelled out
> exactly.

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
- **TLS:** `wp_remote_post` must NOT set `'sslverify' => false`. **Confirmed
  present in the current code** — see below; the new sender must drop it
  (WordPress verifies by default).

## As-built WP sender (verified from theme source, 2026-07-27)

The enquiry POST lives in the theme, wired as an admin-ajax action:

- `villacollective/functions.php` `ajax_enquire_record()` (~line 514,
  `wp_ajax[_nopriv]_ajax_enquire_record`): parses the form, normalises
  (`CountryIds` → CSV, `RegionIds` → array, strips spaces from `ContactNo`,
  `UserFeedback == "Other"` → replaced by `other_text`), saves a local copy
  into `wp_villa_enquiries`, then posts to `API_SITE_URL . "Properties/PostEnquire"`.
- The transport is the shared helper `post_api_call()` in
  `villacollective/api.php` (~line 31): headers `Content-Type:
  application/json` + `X-API-Key: X_API_Key`, and **`'sslverify' => false`
  hardcoded**. Constants (`API_SITE_URL`, `X_API_Key`, `WP_SITE_ENV`) are
  defined in `wp-config.php`, not the theme (good).
- **Success check is `code == 200` AND body `Status`/`status` == true.** Our
  endpoint returns `201 {"reference": …}` — with only a URL/token swap every
  enquiry would be treated as a failure: alert email to Mojo + Nick, failure
  message shown to the customer, even though the lead was created. The WP
  change MUST update the success check, not just the URL.
- **`post_api_call` is shared** by the payment/booking flows that stay on
  legacy (`Payment/PaymentStatus`, `Payment/ConfirmBooking`,
  `Payment/TokenisePaymentStatus`, `Payment/SaveCheckoutInfo`,
  `Properties/ManualInvoiceRequest`, `Properties/Link`). Do NOT edit the
  shared helper or repoint `API_SITE_URL` — add a dedicated function for the
  enquiry post only.
- Client-side gate: the POST only fires when FirstName, LastName, Email,
  FromDate, ToDate and ContactNo are all non-empty (matches what we saw in
  `vc_wp_1.sql` — no fully-empty submissions).
- The form fields match the shapes the serializer pins: hidden
  `Properties`/`RegionIds` default to `"0"`, hidden `RequestType=ENQUIRY`,
  `EnquireDateTypeString` set by JS to the UI labels.
- `WP_Token` is only the **inbound** auth for the ResSystem→WP sync endpoints
  in `api.php` (country/region/villa/booking sync); the outbound header is
  `X-API-Key`. Both are burned; neither is reused.

### Exact change for the WP developer (Mojo)

In `wp-config.php` (values delivered over a secure channel, never committed):

```php
define('VC_RES_ENQUIRY_URL', 'https://<django-host>/api/wordpress/enquiries');
define('VC_RES_API_TOKEN', '<token from bootstrap_wordpress_user>');
```

New function (theme `api.php`) — note: no `sslverify` override, `Token` auth,
201 + `reference` as the success signal:

```php
function post_enquiry_to_vc($data)
{
    $response = wp_remote_post(VC_RES_ENQUIRY_URL, array(
        'body' => $data,
        'headers' => array(
            'Content-Type' => 'application/json',
            'Authorization' => 'Token ' . VC_RES_API_TOKEN,
        ),
    ));
    if (is_wp_error($response)) {
        return false;
    }
    $code = wp_remote_retrieve_response_code($response);
    $body = json_decode(wp_remote_retrieve_body($response));
    return ($code === 201 && !empty($body->reference)) ? $body->reference : false;
}
```

In `ajax_enquire_record()` replace the `Properties/PostEnquire` +
`post_api_call` + `Status` check with:

```php
$reference = post_enquiry_to_vc($post_data);
if ($reference !== false) {
    $status = true;
    $message = "Your enquiry has been sent successfully";
} else {
    // existing error-mail fallback unchanged
}
```

Everything else (local `wp_villa_enquiries` save, error-mail fallback, the
form itself) stays as is. Separately flag to Mojo: `post_api_call`'s
`'sslverify' => false` also disables TLS verification on the **payment**
posts — worth fixing independently of this cutover.

## Smoke test (staging)

```bash
TOKEN=$(cd django_res && uv run python manage.py bootstrap_wordpress_user | grep -o 'Token.*: .*' | awk '{print $NF}')
curl -sS -X POST https://<staging-host>/api/wordpress/enquiries \
  -H "Authorization: Token $TOKEN" -H 'Content-Type: application/json' \
  -d '{"FirstName":"Smoke","Email":"smoke@example.com","Properties":"0","RegionIds":["0"],"EnquireDateTypeString":"Specific dates","FromDate":"2027-05-01","ToDate":"2027-05-08","Adults":"2","IsSignUp":false}'
# → 201 {"reference":"E…"}; repeat within the hour → same reference, no dup.
```

## Cutover checklist

1. WP developer applies the exact change above (dedicated function; do not
   touch `post_api_call` or `API_SITE_URL`). Source received + verified
   2026-07-27.
2. `./manage.py bootstrap_wordpress_user` on production; copy the token to
   `wp-config.php` (secure channel).
3. Ensure `ZOHO_FLOW_WEBHOOK_ENQUIRY` is set in the Django environment if
   WP-originated enquiries should push to Zoho (empty = silently disabled).
4. **Gate:** one real end-to-end submission from the WP staging/live form
   against Django staging before flipping production. (Wire shape verified
   from `vc_wp_1.sql`, sender code verified from the theme source; this
   confirms the *deployed* code matches the source we were sent.)
5. Deploy the theme change + wp-config constants on production. Watch
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
