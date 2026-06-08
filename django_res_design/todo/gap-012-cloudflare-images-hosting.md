# GAP-012 — Object-storage image hosting (Cloudflare Images) for staging & prod

**Severity:** gap (designed-but-half-built; blocks any non-toy image use on
staging/prod).

**Status:** ⬜ open — specced, ready to build. Work branch
`feat/s3-image-hosting` (worktree
`../villacollective-worktrees/s3-image-hosting/`). Provider decided
(**Cloudflare Images**); a few implementation-time decisions remain (below).

**Source:** ad-hoc request 2026-06-08 ("proper S3-bucket-based image hosting for
staging and prod"), refined during planning to **Cloudflare Images** after
weighing a raw R2/S3 bucket. Supersedes the aspirational notes in
`properties/serializers/image.py` (the "FE uploads to the signed URL, then POSTs
the resulting key back" docstring) and `data_migration/CUTOVER.md §8` (legacy
image binaries deferred to a "separate Image migration workstream").

## Problem

All uploaded/seeded media — villa photos (`PropertyImage.image`) and
`Collection.cover_image` — currently lives on the Render container's **ephemeral
local disk** via `FileSystemStorage`, served by
`core.middleware.MediaWhiteNoiseMiddleware` off `/media/`
(`villacollective/settings/base.py:113-118`). That:

- **Doesn't survive restart/redeploy/scale** — Render disks are ephemeral; a new
  container has no uploaded files. Staging masks this with
  `WHITENOISE_AUTOREFRESH=True` + re-running `seed_dev`, but real uploads vanish.
- **Can't hold the ~13k legacy images** the cutover needs.
- **Serves un-resized originals** to every viewport — no thumbnails, no format
  optimisation. A 10 MB phone photo is shipped to a thumbnail grid.

The write path is **half-built for object storage but inert**: the FE form has a
manual "key" text field (no file picker), `PropertyImageWriteSerializer` takes a
`key` string, the view writes it straight into the `ImageField`
(`properties/views/image.py:42`), and `core.models.UploadTicket`
(`core/migrations/0001_initial.py`) scaffolds a presigned-upload reservation —
but **nothing generates an upload URL and nothing stores real bytes anywhere
durable.**

## Decision — why Cloudflare Images over a raw R2/S3 bucket

We are hosted on Render (Frankfurt), so AWS is not a given. Two shapes were
considered:

- **Raw bucket (Cloudflare R2 + `django-storages`/`boto3`).** Swap
  `STORAGES["default"]` to S3, presigned-PUT uploads, public bucket + CDN. Keys
  are portable. **But:** no derivatives/resizing (we'd build or bolt on image
  transforms), presigned-PUT carries real footguns (exact Content-Type header
  matching → 403, CORS signing, R2 addressing-style quirks), and a public bucket
  can't *validate* that an upload is actually an image.
- **Cloudflare Images (chosen).** Managed: stores images, auto-generates named
  resized/format-optimised variants (WebP/AVIF), serves from Cloudflare's CDN,
  issues a one-time **direct-creator-upload** URL (browser → Cloudflare, never
  through gunicorn), and **rejects non-images / over-cap files at upload**. This
  resolves the derivatives gap *and* the presigned footguns in one product.
  **Trade-offs accepted:** vendor lock-in (image IDs aren't portable like S3
  keys; leaving means re-uploading) and **images-only** (no general blob store —
  so comms email attachments are explicitly *not* covered here and would need a
  separate R2/S3 private store).

### How Cloudflare Images works (facts driving the design)

- Each image has an **image ID**; we may supply a **custom ID** (≤1024 chars,
  slashes allowed) — so a legacy key `properties/legacy/<file>` can become the
  CF ID verbatim.
- Delivery URL: `https://imagedelivery.net/<account_hash>/<image_id>/<variant>`,
  where `<variant>` is a named preset configured once per account. **URL
  construction is pure offline string-building** — `account_hash` + id + variant
  — so a 50-image gallery makes **zero** CF calls on read (do not implement
  `image_urls` via per-row `get_image`).
- **Direct creator upload:** server `POST`s `images/v2/direct_upload` →
  `{uploadURL, id}`; browser `PUT`s the file (multipart, field `file`) to that
  one-time URL. CF creates a **draft** record at request time that flips to
  non-draft only after the bytes land.
- Two distinct identifiers: **account ID** (API path `/accounts/<id>/images`)
  and **account hash** (delivery URLs). Both needed.

## Assumptions tested against code (2026-06-08)

| # | Assumption | Verdict | Evidence |
|---|---|---|---|
| 1 | Images live on local `FileSystemStorage` today | ✅ true | `settings/base.py:115-118`; `core/middleware.py` `MediaWhiteNoiseMiddleware` |
| 2 | Write path already key-based (no multipart upload) | ✅ true | `PropertyImageWriteSerializer.key` (`serializers/image.py:35`); view writes `image=data["key"]` (`views/image.py:42`) |
| 3 | `UploadTicket` scaffold exists for the presigned flow | ✅ true | `core/models/upload.py`; migration `core/0001_initial.py`. **But** no view issues one; the `path` field is unused/undefined |
| 4 | No object-storage deps present | ✅ true | no `boto3`/`django-storages` in `django_res/pyproject.toml`; `pillow` is validation-only |
| 5 | FE has a real file picker | ❌ false | `PropertyImageFormDialog.tsx` renders a manual `key` `<Input>`, disabled on edit; no `<input type=file>` |
| 6 | 13k legacy image *rows* loaded; binaries not | ✅ true | `data_migration/loaders/property_children.py` stores `properties/legacy/<file>`; `CUTOVER.md §8` defers binaries |
| 7 | `comms` already has S3 storage | ❌ false | `comms/services.py` `Attachment.storage_key` is a metadata dataclass only — no client, aspirational |

**Greenfield confirmation:** no Cloudflare/S3 client anywhere. Prefer
off-the-shelf (`httpx` for the CF REST client) over hand-rolling, per the
library-first rule.

## Proposed shape

1. **Model.** Replace `PropertyImage.image` (`ImageField`) and
   `Collection.cover_image` with `cloudflare_image_id =
   CharField(max_length=1024, db_index=True)` — **indexed, NOT globally unique**
   (the same photo can legitimately recur across rows). Keep the unique-active-
   hero constraint. Update `core.audit.track(...)` if the field is tracked.
   Migrate in **two phases** (see Open decision D), not a one-shot column drop.

2. **Cloudflare client** — `integrations/cloudflare_images.py` (`integrations`
   is the sanctioned low layer for outbound third-party calls; `properties →
   integrations` is a legal downward edge; `core` must stay import-free so the
   CF-calling code may **not** live in `core`). Methods: `direct_upload()`,
   `get_image(id)`, `delete_image(id)`, `ensure_variants()`. Reads
   `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_IMAGES_API_TOKEN`,
   `CLOUDFLARE_IMAGES_ACCOUNT_HASH`.

3. **Backend abstraction** — `properties/services/images_backend.py`:
   `ImagesBackend` protocol + `CloudflareImagesBackend` and `LocalImagesBackend`
   (FileSystemStorage round-trip; every variant resolves to the same `/media/…`
   URL), selected by `settings.IMAGES_BACKEND`. Keeps **dev/test fully offline**
   (no CF account, no MinIO; network-free tests). Two impls behind one small
   protocol — the deliberate KISS line, not a framework.

4. **Direct-upload endpoint** — `POST /api/v1/images:direct-upload`
   `{filename, content_type, size}` (`IsReservationsWriter`). Validates size cap
   (CF 10 MB) + `image/` prefix, asks the backend for an upload slot, records an
   `UploadTicket(user, key=<image id>, expires_at)`, returns
   `{upload_url, image_id, expires_at}`. New uploads use **CF-generated UUID
   IDs** (returned by `direct_upload`); only the legacy import supplies custom
   path-style IDs. Pass `requireSignedURLs=false` so public delivery URLs work.

5. **Attach** — `properties/views/image.py`: rename wire field `key` →
   `cloudflare_image_id`. **Idempotency by id** (fixes retry/double-click): if a
   `PropertyImage` with this id already exists for the property, return it (200)
   rather than erroring. Otherwise **verify the upload landed** —
   `get_image(id)` requires `draft == false` (local: file exists in
   `MEDIA_ROOT`) — consume the ticket, create the row.

6. **Delete cleanup (was missing).** `PropertyImage`/`Collection` are hard-
   deleted (no soft delete). A `post_delete` signal (and the hero-swap/replace
   paths) calls `backend.delete_image(id)` (swallow 404) so a deleted row
   releases its CF image — CF bills per stored image. `reconcile_images`
   management command lists CF IDs and flags any with no DB row (sweep past
   leaks).

7. **Serializer.** Emit `image_urls` — `{thumbnail, card, hero, full}` built
   offline from `account_hash` + id + variant (or four copies of the `/media`
   URL in `local` mode). FE picks per context. v1 reshape — FE lands together.

8. **Variants.** `ensure_image_variants` management command (idempotent) creates
   the four named variants via the CF API; run once per account.

9. **Settings.** `IMAGES_BACKEND` (`local` default in `base`; `cloudflare` in
   `staging`/`production`; `local` in `dev`/`test`), `MAX_IMAGE_BYTES`,
   `IMAGE_VARIANTS`, the three `CLOUDFLARE_*` reads. **No `STORAGES` change** —
   images bypass Django storage in `cloudflare` mode.

10. **Frontend.** `PropertyImageFormDialog.tsx`: replace the `key` input with
    `<input type="file" accept="image/*">`; flow = requestDirectUpload → PUT
    bytes (progress/error) → existing `createPropertyImage` hook with
    `{cloudflare_image_id, kind, …}`. Switch gallery/hero/lightbox rendering to
    the `image_urls` variant dict.

11. **Legacy import** — `properties/management/commands/import_legacy_images.py`
    `--source <dir-or-url> [--dry-run]`. Upload each legacy binary to CF with
    **custom id = the existing key** (`properties/legacy/<file>`), so DB rows
    resolve with no row edits. Idempotent (single CF `list` + diff, not 13k
    per-object HEADs). Reports uploaded/skipped/source-missing; flags filenames
    that don't match a source file (assumes unique, case-exact names).

## Open decisions (settle at implementation time)

- **A — Staff/prod env isolation.** Deferred to ops at CF account setup:
  separate accounts per env (cleanest) **or** one account with `staging/` /
  `prod/` custom-ID prefixes. Code is env-driven (`CLOUDFLARE_*` per Render env)
  and bakes in **no** prefixing, so this doesn't block build.
- **B — `seed_dev` must not pollute CF.** Staging runs `seed_dev` with
  `IMAGES_BACKEND=cloudflare`, which would upload the committed demo villa-image
  pool to CF every run (storage burn + creds-at-seed-time). **Decide:**
  `seed_dev` always uses the `local` backend (or placeholder URLs) regardless of
  `IMAGES_BACKEND`.
- **C — `UploadTicket`'s reduced role.** With CF returning the id and attach
  verifying via `get_image`/`draft`, the ticket only proves "this user was
  issued this id" + expiry/audit. Keep it for that authz/audit value or drop it
  for KISS — pick one; don't keep scaffolding by inertia. Resolve the unused
  `path` field in the same migration.
- **D — Reversible, two-phase migration.** Mirror the repo's `deprecate_field`
  3-PR convention: PR-A adds + backfills `cloudflare_image_id` and dual-reads;
  drop the old `ImageField` column only in a later PR once CF is proven in prod.
  A one-shot destructive drop on 13k customer-facing rows has no rollback.
- **E — Prod cutover ordering.** The backfill makes every row claim a CF id
  immediately, but binaries aren't in CF until `import_legacy_images` runs (needs
  the `--source` ops prerequisite). **Prod must not switch to `cloudflare` until
  the import has populated CF**, or all 13k villa photos 404 in the window.
  Staging can tolerate the gap.
- **F — `local` PUT view security.** The `local` backend's upload endpoint must
  be staff-only, ticket-scoped, and reject ids containing `../` (path traversal
  into `MEDIA_ROOT`). Dev-only, but it becomes the template.

## Prerequisites (ops)

1. Cloudflare Images-enabled account(s) (staging + prod per decision A); an API
   token scoped to Images; each account hash captured; `ensure_image_variants`
   run per account.
2. Source location of the ~13k legacy `/uploads/` binaries for
   `import_legacy_images --source` (`CUTOVER.md §8` — update it to point here).

## Suggested PR sequencing (keep landings small)

- **PR-A — read path:** model field + two-phase migration (add+backfill+dual-
  read) + `image_urls` serializer + `LocalImagesBackend` + FE variant rendering.
  Ships behind the `local` default; no upload change yet.
- **PR-B — write path:** `images:direct-upload` + `CloudflareImagesBackend` + CF
  client + FE file picker + attach verify/idempotency.
- **PR-C — cleanup:** `post_delete` delete + `reconcile_images`.
- **PR-D — legacy import** + prod cutover + drop the old column.

## Acceptance

- `PropertyImage`/`Collection` store `cloudflare_image_id`; serializer emits four
  variant URLs built offline (no per-row CF call).
- Direct-upload endpoint issues a one-time URL; FE file picker uploads browser →
  CF; attach verifies `draft == false`, is idempotent on id (duplicate → 200),
  rejects expired/foreign tickets.
- Deleting a `PropertyImage` removes the CF image (404 swallowed);
  `reconcile_images` flags orphans.
- `IMAGES_BACKEND=local` gives a fully offline dev/test path; CF client mocked in
  tests (no network). Staging is the real gate for CF-specific behaviour
  (`draft`, `requireSignedURLs`, variant URL shape).
- `import_legacy_images` is idempotent and resolves existing rows with no edits.
- `seed_dev` never writes to CF (decision B).
- Lint/type gate green incl. `lint-imports` (CF client in `integrations`, not
  `core`).

## Dependencies

- **Related:** `data_migration/CUTOVER.md §8` (legacy binaries — repoint here);
  `properties/serializers/image.py` + `core/models/upload.py` (supersedes the
  aspirational presigned scaffolding).
- **Not covered:** comms email-attachment storage (images-only product; needs a
  separate R2/S3 private store) — leave the `comms.Attachment` note as-is.
- **No hard blockers** to PR-A/PR-B beyond the ops prerequisites for the CF
  account; PR-D is gated on the legacy `--source`.
