# GAP-012 — S3 image hosting for staging & prod

**Severity:** gap (blocks any non-toy image use on staging/prod).

**Status:** ⬜ open — specced, ready to build. Work branch
`feat/s3-image-hosting` (worktree
`../villacollective-worktrees/s3-image-hosting/`). **Bucket already created**
(see Infrastructure below).

**Source:** ad-hoc request 2026-06-08 ("proper S3-bucket-based image hosting
for staging and prod"). An earlier revision of this doc specced **Cloudflare
Images** (managed variants, direct creator upload); on 2026-06-10 the decision
was reversed to **plain S3, kept deliberately simple**: no resizing/variants in
this version, uploads proxied through Django (no presigned URLs), serve
originals from public S3 URLs. Supersedes the aspirational notes in
`properties/serializers/image.py` (the "FE uploads to the signed URL, then
POSTs the key back" docstring) and `data_migration/CUTOVER.md §8` (legacy image
binaries deferred to a "separate Image migration workstream").

## Problem

All uploaded/seeded media — villa photos (`PropertyImage.image`) and
`Collection.cover_image` — lives on the Render container's **ephemeral local
disk** via `FileSystemStorage`, served by
`core.middleware.MediaWhiteNoiseMiddleware` off `/media/`
(`villacollective/settings/base.py:113-118`). That:

- **Doesn't survive restart/redeploy/scale** — a new container has no uploaded
  files. Staging masks this with `WHITENOISE_AUTOREFRESH=True` + re-running
  `seed_dev`, but real uploads vanish.
- **Can't hold the ~13k legacy images** the cutover needs.

The write path is half-built for object storage but inert: the FE form has a
manual "key" text field (no file picker), `PropertyImageWriteSerializer` takes
a `key` string, the view writes it straight into the `ImageField`
(`properties/views/image.py:42`), and `core.models.UploadTicket` scaffolds a
presigned-upload reservation that nothing issues.

## Decision — plain S3 via `django-storages`, uploads through Django

The simplest shape that solves durability:

- **Keep the `ImageField`s.** `django-storages` swaps the *storage backend*
  under the existing fields — **no model migration** for `PropertyImage.image`
  or `Collection.cover_image`, and existing keys
  (`properties/legacy/<filename>`) stay valid.
- **Uploads go through Django** as ordinary multipart POSTs. No presigned-PUT
  flow (and none of its Content-Type/CORS footguns), no `UploadTicket`, no
  draft-verification dance. A ≤10 MB image through gunicorn is fine at this
  project's scale. `ImageField` + Pillow already validates uploads are real
  images.
- **No resizing/variants in this version.** Originals are served as-is from
  public S3 URLs. CDN/derivatives are a future, separate concern (CloudFront
  and/or a resize layer) — explicitly out of scope here.
- **Trade-offs accepted:** un-resized originals shipped to every viewport
  (status quo, just durable now), upload bytes transit gunicorn, and no
  upload-time CDN goodies. All reversible later without touching the data
  model.

## Infrastructure (done 2026-06-10)

| Item | Value |
|---|---|
| Bucket | `villacollective-images` (`arn:aws:s3:::villacollective-images`) |
| Region | `eu-central-1` (Frankfurt — matches Render) |
| Account | `235208471728` (personal — **never** the Canary dayjob profiles) |
| Public access | Objects world-readable via bucket policy (`s3:GetObject` on `…/*`); ACLs blocked (`BlockPublicAcls`/`IgnorePublicAcls` true); writes require IAM credentials |
| URL shape | `https://villacollective-images.s3.eu-central-1.amazonaws.com/<key>` |
| CLI profile | `villacollective-dev` (IAM user `villacollective-cli`) — pass `--profile` explicitly on every call |

Verified: authenticated write + anonymous read + delete round-trip.

**Env isolation:** one bucket, prefix per environment via django-storages'
`AWS_LOCATION` — `staging/` and `production/`. Keys in the DB stay
prefix-free; the prefix is applied by the storage layer, so the same row works
in both envs.

**Still to do (ops):** create an app-scoped IAM user (e.g.
`villacollective-app`) with put/get/delete/list limited to this bucket, and
set its keys as Render env vars per service. Do not ship the
`villacollective-cli` user's keys to Render.

## Proposed shape

1. **Dependencies.** `uv add django-storages[s3]` (pulls `boto3`).

2. **Settings.** In `base.py`, keep `FileSystemStorage` as the default. In
   `staging.py`/`production.py`, set `STORAGES["default"]` to
   `storages.backends.s3.S3Storage` with:
   - `AWS_STORAGE_BUCKET_NAME=villacollective-images`,
     `AWS_S3_REGION_NAME=eu-central-1`
   - credentials from env (`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`)
   - `AWS_LOCATION` = `staging` / `production`
   - `AWS_QUERYSTRING_AUTH=False` (plain public URLs, no signing per read)
   - `AWS_DEFAULT_ACL=None` (bucket policy handles public read; ACLs are
     blocked)
   - `AWS_S3_FILE_OVERWRITE=False` (collide → auto-suffix, never clobber)
   Dev and test keep local storage — **fully offline, no AWS account needed,
   no mocking of S3 in tests** beyond what `FileSystemStorage` already gives.

3. **Write path.** `PropertyImageWriteSerializer`: replace the `key` CharField
   with a real `ImageField` (multipart upload); enforce `MAX_IMAGE_BYTES`
   (10 MB) in `validate_image`. View saves the file through the field —
   storage backend decides where bytes land. Same change for
   `Collection.cover_image` writes.

4. **Drop `UploadTicket`** (`core/models/upload.py` + migration). It existed
   for a presigned flow we are not building. Resolves the old open decision
   about its unused `path` field by deleting the model.

5. **Read path.** Serializers emit a single absolute `image_url`
   (`obj.image.url` — storage-generated; `/media/…` locally, S3 URL on
   staging/prod). No variant dict.

6. **Delete cleanup.** `post_delete` signal on `PropertyImage` (and the
   `Collection.cover_image` replace path) calls
   `instance.image.delete(save=False)` — works identically for local and S3
   backends, so a hard-deleted row doesn't leak a stored object.

7. **Frontend.** `PropertyImageFormDialog.tsx`: replace the manual `key`
   `<Input>` with `<input type="file" accept="image/*">`; submit multipart to
   the existing create endpoint. Render images from the serializer's
   `image_url`.

8. **Legacy import** — `properties/management/commands/import_legacy_images.py`
   `--source <dir> [--dry-run]`. For each `PropertyImage` row whose key starts
   with `properties/legacy/`, upload the source binary to the row's existing
   key via `default_storage` (so `AWS_LOCATION` prefixing applies
   automatically) and the row resolves with **no row edits**. Idempotent: one
   `list_objects` of the prefix + diff, not 13k per-object HEADs. Reports
   uploaded / skipped / missing-at-source; treat missing-at-source as the
   expected-loss bucket — log, don't crash.

   **Nested-source → flat-target reconstruction (load-bearing).** The legacy
   .NET app stores files **nested under the integer villa id**:
   `wwwroot/PropertyImages/<VillaId>/<filename>` (`Component.cs:213,219,239`;
   served at `/PropertyImages/<VillaId>/<file>`, `Booking.razor:89`). The
   loader (`data_migration/loaders/property_children.py`) kept the filename
   but **dropped the `<VillaId>` subfolder**, storing a flat
   `properties/legacy/<filename>` key — so the row alone cannot locate its
   source file. Rebuild per row:

   | Need | Source |
   |---|---|
   | target key | `PropertyImage.image` = `properties/legacy/<filename>` (flat) |
   | `<filename>` | tail of `image` (= legacy `VillaPropertyImages.Name`) |
   | `<VillaId>` (source subfolder) | `PropertyImage.property.legacy_id` (= legacy `VillaMaster.Id`) — **not** in the `image` string |

   So the copy is `PropertyImages/<property.legacy_id>/<filename>` → key
   `properties/legacy/<filename>`. Worked example (2026-06-09):
   `properties/legacy/9436180e-…-58fe3e02bc64.jpg` on a property with
   `legacy_id=1` came from `wwwroot/PropertyImages/1/9436180e-….jpg`.

   **Flatten-collision check (re-run per dump).** Flattening is only safe if
   filenames are globally unique across villas. Verified 2026-06-09: **12,293
   rows, 12,293 distinct keys, 0 collisions** (legacy `Name` values are
   GUIDs). A property of the data, not a guarantee — re-verify on the cutover
   dump; a single colliding `Name` would make two rows resolve to one image,
   silently overwriting.

   **Source files are not in the repo/container** —
   `res-app:/app/wwwroot/PropertyImages` is empty and the path is gitignored;
   ops must export the archived legacy tree for `--source` (see Prereqs).

## Open decisions (settle at implementation time)

- **A — `seed_dev` writes to S3 on staging.** With S3 as staging's default
  storage, every `seed_dev` run uploads the committed demo image pool. The
  pool is small and `AWS_S3_FILE_OVERWRITE=False` suffixes duplicates, so the
  simplest acceptable answer may be "let it" — but check the seeder doesn't
  balloon the `staging/` prefix across repeated runs (delete-and-reseed, or
  deterministic filenames).
- **B — Prod cutover ordering.** Once prod's storage flips to S3, every
  legacy row's URL points at S3 immediately, but binaries aren't there until
  `import_legacy_images` runs (needs the `--source` ops prerequisite). **Run
  the import into `production/` before flipping prod**, or all 13k villa
  photos 404 in the window. Staging can tolerate the gap.

## Prerequisites (ops)

1. ~~S3 bucket + public-read policy~~ — **done** (see Infrastructure).
2. App-scoped IAM user; keys into Render env vars (staging + prod services).
3. Source export of the ~13k legacy binaries for `import_legacy_images
   --source` (`CUTOVER.md §8` — update it to point here).

## Suggested PR sequencing

- **PR-A — storage + write path:** `django-storages` settings, multipart
  upload serializer/view, drop `UploadTicket`, `image_url` read path,
  `post_delete` cleanup, FE file picker + rendering. Dev/test stay on local
  storage; staging flips via env.
- **PR-B — legacy import:** `import_legacy_images` + collision re-check +
  prod cutover (ordering per decision B).

## Acceptance

- Uploading via the FE file picker stores bytes in
  `villacollective-images/<env>/…` on staging/prod and in `MEDIA_ROOT`
  locally; the file survives a redeploy.
- Serializers emit a working absolute `image_url` in both modes.
- Upload rejects non-images and files > 10 MB.
- Deleting a `PropertyImage` removes the stored object (both backends).
- `UploadTicket` is gone.
- Dev/test run fully offline; no AWS credentials or mocks required.
- `import_legacy_images` is idempotent, reports
  uploaded/skipped/missing-at-source, and resolves existing rows with no row
  edits.
- Lint/type/test gate green.

## Dependencies

- **Related:** `data_migration/CUTOVER.md §8` (legacy binaries — repoint
  here); `properties/serializers/image.py` + `core/models/upload.py`
  (superseded presigned scaffolding).
- **Not covered:** image resizing/variants and CDN (future work);
  comms email-attachment storage (would want a *private* bucket/prefix —
  leave the `comms.Attachment` note as-is).
- **No hard blockers** to PR-A; PR-B is gated on the legacy `--source` export
  and the Render IAM keys.
