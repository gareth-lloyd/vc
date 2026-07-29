# Villa Collective — WP enquiry form: point at the new reservations system

Handoff package for Mojo Media. The enquiry form currently posts to the old
reservations system (`Properties/PostEnquire` via `post_api_call`). The new
Django-based system is live and ready to receive; this package retargets the
enquiry POST only — **payments and everything else stay on the old system
and are untouched**.

What changes:

- New endpoint + new auth: `POST https://<host>/api/wordpress/enquiries`
  with an `Authorization: Token …` header (replaces `X-API-Key`).
- New success contract: the new system replies `201` with
  `{"reference": "E…"}` — not the old `{Status, Message, Data}` envelope.
  Resubmitting the identical form within the hour is safe: the server
  replays the same `201`/reference instead of creating a duplicate.
- A dedicated `post_enquiry_to_vc()` function is added to the theme's
  `api.php`. The shared `post_api_call()` helper is deliberately **not**
  modified or repointed — it still serves the payment/booking flows on the
  old system.
- The form payload itself is unchanged; the enquiry handler in
  `functions.php` swaps the transport call and success check, and defaults
  `RegionIds` for the contact/wishlist forms (they have no region field, and
  the current code turns that into `[null]` on the wire).
- TLS verification is ON for the new call (no `'sslverify' => false`).

## Files in this package

| File | What it is |
| --- | --- |
| `api.php` | Full modified copy of the theme file (adds `post_enquiry_to_vc()`) |
| `functions.php` | Full modified copy (enquiry handler changes only) |
| `enquiry-endpoint.patch` | The same changes as a unified diff of both files |
| `optional-tls-fix.patch` | **Separate, optional** — see below; not required for the cutover |

Both modified copies were made against the theme source you sent us on
2026-07-27 (`wetransfer_remaining-plugins-zip`). If the deployed theme has
drifted since, prefer the patch over the drop-in copies.

## How to apply

Either:

- **Drop-in:** replace the theme's `api.php` and `functions.php` with the
  copies in this folder (after diffing against what's deployed), or
- **Patch:** from the theme root
  (`wp-content/themes/villacollective/`):

  ```sh
  patch -p1 --dry-run < enquiry-endpoint.patch   # check first
  patch -p1 < enquiry-endpoint.patch
  ```

The two patches are independent: each applies on its own, in either order,
and `optional-tls-fix.patch` also applies on top of the drop-in `api.php`.

## wp-config.php constants

The new function reads two constants from `wp-config.php` (never the theme,
never the database, never committed anywhere). The real values are delivered
separately over a secure channel.

**Dev site (test against our staging system):**

```php
define('VC_RES_ENQUIRY_URL', 'https://<staging-host>/api/wordpress/enquiries');
define('VC_RES_API_TOKEN', '<staging token — delivered separately>');
```

**Live site (at cutover):**

```php
define('VC_RES_ENQUIRY_URL', 'https://<production-host>/api/wordpress/enquiries');
define('VC_RES_API_TOKEN', '<production token — delivered separately>');
```

These are **two different sets of values** — do not copy the dev site's
constants to live. Staging and production have different URLs *and*
different tokens. Also note: no trailing slash on the URL (a trailing slash
returns 404).

If the constants are missing, the code degrades safely: the enquiry is still
saved to the local `wp_villa_enquiries` table and the existing error-mail
fallback fires; nothing fatals.

## Test procedure (dev site first)

1. Apply the code change on the **dev site** (it's detached from the res
   feeds, so it's safe) with the **staging** constants.
2. Submit the enquiry form normally. Expect the usual success message.
3. Tell us — we'll confirm the lead arrived on our side with the right
   fields.
4. Submit the identical form again within the hour. Expect success again,
   and we confirm **no duplicate** was created.
5. Optionally repeat once from the contact page and the wishlist page (they
   share the same handler).
6. Once that gate passes, apply the same code change on **live** with the
   **production** constants at the agreed cutover time.

Notes for testing:

- The first request after a quiet period can be slow (~15–30s) while our
  hosting spins up; the call timeout is set to 30s to cover it. If a
  submission does time out, the failure path fires (error mail + failure
  message) but a resubmit within the hour is safe — no duplicate.
- The failure path still sends the existing alert email to the hardcoded
  recipients (connectusdemo12, ben@mojomedia, mungraurvish, cc nick) — so
  expect a few of those while testing failure cases; they're not a problem
  with the new system.
- Failures are also logged to PHP `error_log` and to the theme's existing
  `wp-content/my-custom-log.json` (event `vc_enquiry_failed`, with the HTTP
  status + response body).

## Rollback

Restore the two original files (the source you sent us is the rollback
state) — the form immediately posts to the old system again. The wp-config
constants are harmless if left in place.

## Optional: `optional-tls-fix.patch`

Separate issue, **not required for the enquiry cutover**: the shared
`post_api_call()` helper hardcodes `'sslverify' => false`, which disables
TLS certificate verification on the **payment/booking** posts to the old
system. The patch mirrors `get_api()`'s existing pattern (verify everywhere
except `WP_SITE_ENV == 'Local'`).

⚠️ Before deploying it, confirm the old system's host presents a valid
certificate for the exact hostname in `API_SITE_URL` — if it doesn't, the
payment calls will start failing. Deploy separately from the enquiry change
(or not at all); it's independent.

## Questions

Anything unclear or if the deployed theme differs from what you sent us:
reply to Gareth / Nick.
