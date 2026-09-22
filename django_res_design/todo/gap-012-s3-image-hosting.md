# GAP-012 — S3 image hosting for staging & prod

**Severity:** gap (blocks any non-toy image use on staging/prod).

**Status:** 🟨 code complete, **execution tracked in
[GAP-120](done/gap-120-staging-legacy-load-and-images.md)** (2026-09-21). Done:
PR-A (storage settings, multipart upload, `image_url` read path, `UploadTicket`
dropped, `post_delete` cleanup, FE file picker), PR-B (`import_legacy_images`,
`0ed2502f`), PR-C (`fetch_legacy_images`, 2026-09-20); the legacy binaries are
fetched (18,232 files, 0 missing) and backed up; buckets split per environment
and the production buckets created; `villacollective-app-staging` created; both
open decisions settled; the 18,232 binaries are **in the staging bucket**
(2026-09-21, `staging/properties/legacy/`, 10.97 GB, 0 missing); staging runs
on the `villacollective-app-staging` keys (2026-09-22) and GAP-120 is resolved.
**Remaining, all ops, production only:** create `villacollective-app-prod`,
server-side `aws s3 sync` of the staging legacy prefix into the prod bucket,
`import_legacy_images --dry-run` under production settings (CUTOVER §8). This
file is now the reference for *how* image storage works; GAP-120 keeps the
staging recipe. Close this ticket when the production import has run.

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
- **Can't hold the 18,232 legacy images (~10.3 GB)** the cutover needs.

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
| Staging bucket | `villacollective-images` (`arn:aws:s3:::villacollective-images`), prefix `staging/` |
| Production bucket | `villacollective-images-prod` (created 2026-09-21), prefix `production/` — same public-read policy / ACL block / AES256, **plus versioning** with noncurrent versions expiring after 90 days |
| Region | `eu-central-1` (Frankfurt — matches Render) |
| Account | `235208471728` (personal — **never** the Canary dayjob profiles) |
| Public access | Objects world-readable via bucket policy (`s3:GetObject` on `…/*`); ACLs blocked (`BlockPublicAcls`/`IgnorePublicAcls` true); writes require IAM credentials |
| URL shape | `https://<bucket>.s3.eu-central-1.amazonaws.com/<env prefix>/<key>` |
| CLI profile | `villacollective-dev` (IAM user `villacollective-cli`) — pass `--profile` explicitly on every call |

Verified: authenticated write + anonymous read + delete round-trip.

**Env isolation (revised 2026-09-21): a bucket per environment**, not
prefixes in one bucket. `production.py` names `villacollective-images-prod`;
`staging.py` overrides it back to `villacollective-images` (pinned by
`core/tests/test_staging_settings.py`). Why: the staging reset is an
`aws s3 rm --recursive`, one path segment from production in a shared bucket;
bucket-scoped IAM policies are trivially correct where prefix-scoped ones are
not; and only production wants versioning (an app-side image delete removes
the object — versioning is the undo). The `staging/` / `production/` prefixes
stay. Keys in the DB are bucket- and prefix-free, so the same row works in
both envs.

**Documents buckets (GAP-094), same split:** staging uses
`villacollective-documents` (prefix `staging/`); production uses
`villacollective-documents-prod` (created 2026-09-21: all public access
blocked, TLS-only bucket policy, AES256, versioning, noncurrent versions expire
after 90 days). The name reaches Django via the `DOCUMENTS_S3_BUCKET` env var,
so the production service must set `DOCUMENTS_S3_BUCKET=villacollective-documents-prod`.

**One app-scoped IAM user per environment.** Staging on Render runs on
`villacollective-app-staging` since 2026-09-22 (GAP-120 step 2); the
`villacollective-cli` keys are on no Render service, and must never be.
`villacollective-app-prod` is still to create (console only).

| User | Images bucket | Documents bucket |
|---|---|---|
| `villacollective-app-staging` | `villacollective-images` | `villacollective-documents` |
| `villacollective-app-prod` | `villacollective-images-prod` | `villacollective-documents-prod` |

Inline policy (`s3-own-buckets`) — substitute the two bucket names. These four
actions are everything django-storages needs (`ListBucket` is what makes
`exists()` return a clean 404). Deliberately **no `s3:DeleteObjectVersion`**:
on the versioned prod buckets an app-side delete only adds a delete marker, so
neither the app nor a leaked key can destroy an object permanently.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Sid": "ListOwnBuckets", "Effect": "Allow",
      "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
      "Resource": ["arn:aws:s3:::<IMAGES_BUCKET>", "arn:aws:s3:::<DOCUMENTS_BUCKET>"] },
    { "Sid": "ReadWriteDeleteOwnObjects", "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": ["arn:aws:s3:::<IMAGES_BUCKET>/*", "arn:aws:s3:::<DOCUMENTS_BUCKET>/*"] }
  ]
}
```

```bash
export AWS_PROFILE=villacollective-dev   # personal account 235208471728 only
ENV=staging   # then again with ENV=prod
aws iam create-user --user-name villacollective-app-$ENV \
    --tags Key=project,Value=villacollective Key=env,Value=$ENV
aws iam put-user-policy --user-name villacollective-app-$ENV \
    --policy-name s3-own-buckets --policy-document file://villacollective-app-$ENV.json
# Prints the secret ONCE — paste straight into that environment's Render
# service as AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY; never commit it.
aws iam create-access-key --user-name villacollective-app-$ENV
```

After swapping staging's keys, confirm a staging image upload and a contract
download still work.

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

   **Downstream consumer (noted 2026-09-01):** `Property.hero_image_url()`
   feeds the Zoho villa payload's `hero_image_url`, and Limitless flagged on
   the villa-sync demo that the value arrives with no domain — expected, since
   that is the local `/media/…` form pre-S3. They have parked it in a plain
   text field, which is the right call; it becomes a usable link once this
   ticket's staging/prod cutover runs. No Flow-side change needed and nothing
   to raise with them. See CHECK-003.

6. **Delete cleanup.** `post_delete` signals on `PropertyImage` and
   `Collection` queue the stored file's deletion via `transaction.on_commit`
   (works identically for local and S3 backends), so a hard-deleted row
   doesn't leak a stored object. Deferring to commit matters twice over:
   `post_delete` fires *inside* the deleting transaction, so an immediate
   delete would run S3 HTTP calls while holding the DB connection, and a
   rollback after the receiver ran would leave a surviving row whose object
   is gone (dangling key).

7. **Frontend.** `PropertyImageFormDialog.tsx`: replace the manual `key`
   `<Input>` with `<input type="file" accept="image/*">`; submit multipart to
   the existing create endpoint. Render images from the serializer's
   `image_url`.

8. **Legacy import** — `properties/management/commands/import_legacy_images.py`
   `--source <dir> [--dry-run]`. For each `PropertyImage` row whose key starts
   with `properties/legacy/`, upload the source binary to the row's existing
   key via `default_storage` (so `AWS_LOCATION` prefixing applies
   automatically) and the row resolves with **no row edits**. Idempotent: one
   `list_objects` of the prefix + diff, not 18k per-object HEADs. Reports
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
   filenames are globally unique across villas. Verified on the loaded data
   2026-09-20: **18,232 rows, 18,232 distinct keys, 0 collisions** (legacy
   `Name` values are GUIDs), and **18,232 distinct case-insensitively** too —
   which matters because two keys differing only in case are distinct rows in
   Postgres and distinct S3 objects but ONE file on a case-insensitive
   filesystem. The 2026-06-09 figure in an earlier revision of this doc (12,293)
   predates the full load. A property of the data, not a guarantee: both
   commands re-check it as a pre-flight and abort before doing any work.

   **Source of the binaries — HTTPS from the legacy host (primary).**
   `res-app:/app/wwwroot/PropertyImages` is empty in the repo/container and the
   path is gitignored, but the legacy .NET app serves every file publicly from
   `https://vc2.mojodev.co.uk/PropertyImages/<VillaId>/<filename>` (hardcoded at
   `PropertyService2.cs:766`). `fetch_legacy_images` downloads that tree into the
   nested layout `import_legacy_images --source` expects, so **no ops export is
   needed** — see runbook step 2a. An ops export of the `res-app-images` Docker
   volume remains the fallback if the legacy host is retired first.

   **Trap, verified:** a *directory* URL answers **HTTP 200 with the Blazor SPA
   shell**, not a listing. A 200 does not mean an image, there is no directory
   enumeration, and so the DB row set is the only manifest.

## Open decisions (settle at implementation time)

- **A — `seed_dev` writes to S3 on staging. ✅ resolved (2026-06-10): let
  it.** Each run is ~270 PUTs (default `--scale small`: 30 properties × ~9
  images from the 11 MB committed pool), adding ~10–30 s; `file_overwrite`
  False suffixes repeated filenames, so the `staging/` prefix grows
  monotonically — pennies/month. Hygiene rule: when resetting the staging DB,
  also wipe the prefix, **except the legacy photos** (`aws s3 rm --recursive
  s3://villacollective-images/staging/ --exclude "properties/legacy/*"`) —
  seeded rows and objects reset together, while the 11 GB under
  `properties/legacy/` (uploaded 2026-09-21, GAP-120 step 5) belongs to the
  legacy load and takes ~1.5 h to put back. *Revised 2026-09-21; the original
  rule wiped the whole prefix.* Rows seeded *before* the S3 flip point at objects that never
  reached S3, so reset + reseed staging once after the cutover deploy.
- **B — Prod cutover ordering.** Once prod's storage flips to S3, every
  legacy row's URL points at S3 immediately, but binaries aren't there until
  `import_legacy_images` runs (needs the `--source` ops prerequisite). **Run
  the import into `production/` before flipping prod**, or all 18,232 villa
  photos 404 in the window. Staging can tolerate the gap.

## Prerequisites (ops)

1. ~~S3 bucket + public-read policy~~ — **done** (see Infrastructure).
2. App-scoped IAM user; keys into Render env vars (staging + prod services).
   **This is the only remaining ops blocker.**
3. ~~Source export of the ~13k legacy binaries~~ — **no longer required.**
   `fetch_legacy_images` produces the `--source` tree itself over HTTPS
   (runbook step 2a). Keep the fetched archive as a cold archive afterwards: it
   is the only copy outside a legacy host that is a retirement candidate, and
   re-fetching costs another 10.3 GB of the supplier's egress.

## Cutover runbook (PR-B)

0. **The flip is not a separate deploy.** `settings/production.py` on main
   already selects S3 storage, so the **next prod push of main flips prod,
   whatever its motivation**. First confirm the prod service's current deploy
   state; until step 2 has run, pushing main to the prod Render service is
   gated on it (and on the AWS env vars being set) — fold this into the
   existing "check Render env vars before pushing" habit.
1. **Prereqs** (above): per-environment app-scoped IAM users
   (`villacollective-app-staging` / `-prod`, each limited to its own bucket)
   with keys in that environment's Render env vars. Never ship the `villacollective-cli` user's keys
   to Render. No ops export is needed — step 2a fetches the binaries.
2a. **Fetch the legacy binaries** (**done 2026-09-20/21**: 18,232 files,
   10.97 GB, 0 missing / rejected / failed; needs no AWS credentials and never
   writes to the database). Measured 2026-09-20 on a 200-file smoke run
   through this command: **3.33 files/s, 14.7 Mbps** at the default concurrency
   8, mean file 551 KB — faster than the 2.11 files/s the original `curl`
   benchmark suggested, because `curl` negotiated HTTP/2 while `httpx` here uses
   keep-alive HTTP/1.1 (`h2` is deliberately not installed):

   ```bash
   # Pre-flight only, ~2 seconds: validates the data and the destination.
   uv run python manage.py fetch_legacy_images --dry-run
   # Watched smoke run — confirm real throughput before committing hours.
   uv run python manage.py fetch_legacy_images --limit 200
   # The real thing. `caffeinate -i` because system sleep kills the run;
   # tmux because a closed terminal SIGHUPs it. Run it OFF-PEAK.
   caffeinate -i uv run python manage.py fetch_legacy_images
   # Then confirm the tree is complete *through the actual consumer*:
   uv run python manage.py import_legacy_images \
       --source ~/villacollective-legacy/PropertyImages --dry-run
   ```

   Expect `downloaded + skipped + missing == 18232` and `missing at source 0`
   from the dry-run. Interrupt and re-run freely — it resumes from the
   filesystem. If the host starts to struggle, Ctrl-C and re-run with
   `--concurrency 4 --delay 0.25`.

   **What the full run actually did:** ~5 h 09 m wall clock, not the ~1.5 h the
   smoke run implied — but about 3 hours of that was dead time, most likely
   the operator's laptop being closed and reopened mid-run (`caffeinate -i`
   does not prevent lid-close sleep). The first 55 minutes moved ~13,400
   files, so ~1.5 h is still the right budget on a machine that stays awake.
   After a sleep the open connections are dead but never closed, so the run
   waits rather than failing; Ctrl-C and re-run — it resumes. Keep the lid
   open (or use a desktop / `caffeinate -s` on mains power).
   Content check: 18,216 JPEG, 12 PNG, 4 WebP (the WebP are named `.jpeg`, all
   villa 412; S3 will label them `image/jpeg`, which browsers tolerate).

   **This hits a third party's live production server.** It is their bandwidth
   (~10.3 GB, which a hosting plan may cap) and their users' web server, so run
   it off-peak, leave the concurrency cap alone, and watch the first 200 files.
   Sustained connections from one IP can trip a bot rule and block you — if that
   happens, stop and wait; do not switch IPs. The command sends an identifying
   User-Agent and stops itself after a run of consecutive failures. One-time
   only: never scheduled, never Celery-wrapped.
2. **Import into `villacollective-images-prod/production/` before the flip-carrying push** — from the
   operator's machine (the source dir is local, not on Render):

   ```bash
   export DJANGO_SETTINGS_MODULE=villacollective.settings.production
   export DATABASE_URL=<Render prod external connection string>
   export AWS_ACCESS_KEY_ID=… AWS_SECRET_ACCESS_KEY=…
   # plus whatever else production.py fails fast on — check the file at run
   # time; real-or-dummy is fine, the command never touches them.
   uv run python manage.py import_legacy_images \
       --source ~/villacollective-legacy/PropertyImages --dry-run
   uv run python manage.py import_legacy_images \
       --source ~/villacollective-legacy/PropertyImages
   ```

   Record the uploaded / skipped / missing-at-source counts; missing-at-source
   is the documented expected-loss bucket. A collision abort means the cutover
   dump broke the GUID-uniqueness property — stop and investigate.
3. **Push/deploy prod**; smoke-test one legacy `image_url` and one fresh FE
   upload.
4. **Staging hygiene** (resolved decision A): rows seeded before staging's
   flip point at objects that never reached S3 —
   `aws s3 rm --recursive s3://villacollective-images/staging/ --exclude
   "properties/legacy/*" --profile villacollective-dev`, reset the staging DB,
   re-run `seed_dev`. **Superseded 2026-09-21:** staging now holds the legacy
   load (GAP-120), so `seed_dev` must not run there again; the `--exclude`
   stays on any future wipe.
5. Re-run the import any time for stragglers — it is idempotent.

## Local dev — serving the legacy images

Dev uses `FileSystemStorage` (no S3, no AWS credentials), so the legacy rows
404 locally until the binaries sit under `MEDIA_ROOT/properties/legacy/`.
`MEDIA_ROOT` is per checkout, so keep **one** flat copy outside the repo and
symlink it into each checkout (WhiteNoise and `FileSystemStorage` both follow a
symlinked directory):

```bash
# Once per machine (~11 GB, under a minute from the local archive):
mkdir -p ~/villacollective-legacy/media-legacy
make link-legacy-media
cd django_res && uv run python manage.py import_legacy_images \
    --source ~/villacollective-legacy/PropertyImages
# Once per additional worktree (no copy, no disk):
make link-legacy-media
```

`django_res/media/` is gitignored, so the link never shows in `git status` and
a fresh clone/worktree needs `make link-legacy-media` again. Only a DB loaded
from the legacy migration has these rows — a `seed_dev` DB has nothing to show.
Deleting a legacy `PropertyImage` locally removes its file from the shared
folder (`post_delete` cleanup); re-run the import to restore it.

## Suggested PR sequencing

- **PR-A — storage + write path:** `django-storages` settings, multipart
  upload serializer/view, drop `UploadTicket`, `image_url` read path,
  `post_delete` cleanup, FE file picker + rendering. Dev/test stay on local
  storage; staging flips via env.
- **PR-B — legacy import:** `import_legacy_images` + collision re-check +
  prod cutover (ordering per decision B).
- **PR-C — legacy fetch:** `fetch_legacy_images` + the shared
  `properties/services/legacy_images.py` pre-flight predicates. Removes the ops
  export prerequisite; the upload half is unchanged.

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
- `fetch_legacy_images` produces that command's `--source` tree, resumes after
  an interrupt without re-downloading, refuses a destination inside the repo,
  and aborts before any request on colliding / case-colliding / unsafe paths.
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
