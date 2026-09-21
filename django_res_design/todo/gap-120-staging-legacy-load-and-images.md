# GAP-120 — Legacy data + legacy images on staging

**Severity:** gap (ops programme — almost no code; the tools all exist).

**Status:** 🟨 filed 2026-09-21; steps 1, 4, 5 and 6 done the same day (`main`
pushed, legacy database restored to staging, 18,232 photos uploaded, reset rule
fixed). **Open: step 2 (key swap), step 3 (personal-data checks — urgent, real
client data is on staging) and step 7 (smoke test).** This ticket is the ordered checklist for getting a
legacy-loaded database and the 18,232 legacy villa photos onto the Render
staging service, and it is the dress rehearsal for the production cutover
(`django_res/data_migration/CUTOVER.md`).

**Source:** GAP-012 close-out, 2026-09-21. GAP-012 keeps the *how* of image
storage (buckets, IAM, the fetch/import commands); this ticket owns the *doing*.

## Where things stand (2026-09-21)

| Thing | State |
|---|---|
| Legacy image archive | ✅ `~/villacollective-legacy/PropertyImages/` — 18,232 files, 10.97 GB, 0 missing; backed up |
| Local dev serving | ✅ `make link-legacy-media` (GAP-012 §Local dev) |
| Staging buckets | ✅ `villacollective-images` + `villacollective-documents`, prefix `staging/` |
| Production buckets | ✅ `villacollective-images-prod` + `villacollective-documents-prod` (versioned), empty |
| IAM `villacollective-app-staging` | ✅ created, policy verified, one active key |
| IAM `villacollective-app-prod` | ⬜ not created (console only — the CLI user cannot write IAM) |
| Staging Render keys | ⬜ still the `villacollective-cli` user's keys |
| `main` | ✅ pushed at `bea09ed6` (2026-09-21). Deploys **staging only** (`render.yaml` → `settings.staging`); no production service exists yet |
| Staging database | ✅ legacy load restored 2026-09-21 — verified `18232` images / `386` properties / `78` migrations. Passwords scrubbed (all unusable); needs `createsuperuser` |
| Staging images | ✅ uploaded 2026-09-21 — 18,232 objects, 10.97 GB under `villacollective-images/staging/properties/legacy/`; re-run dry-run says `uploaded 0, skipped 18232`; anonymous GET → 200 `image/jpeg` |

## Next steps, in order

1. ✅ **Push `main`** — done 2026-09-21. The deploy stopped on
   `rateplan_one_active_per_regime` (duplicate seed rows), as predicted; the
   step-4 restore replaced the database, which cleared it.
2. **Swap staging's AWS keys** in Render to `villacollective-app-staging`.
   Verify: upload an image in the staging SPA, download a contract. Then the
   `villacollective-cli` keys are off Render for good.
3. **Pre-flight the personal-data question (blocking — see below).**
4. ✅ **Load the legacy data: build locally, restore to staging** — done
   2026-09-21. `reconcile_legacy --integrations` exited 0 locally (64 OK, 8
   INFO); dump restored and verified on staging. The repeatable recipe, with
   what bit us:
   - **Dump a scrubbed copy, not the dev DB.** `createdb -T villacollective
     vc_scrub`, set every `accounts_user.password` unusable, `pg_dump -Fc
     --no-owner --no-acl`, drop the copy. Real staff hashes never leave the
     laptop. Dumps live in `~/villacollective-legacy/db-dumps/` (mode 600, real
     client data — never in the repo, never in S3).
   - **Staging's DB has `ipAllowList: []`** (no external access, deliberate).
     Add your `/32` in the Render dashboard for the restore and remove it after;
     do not put an IP in `render.yaml`.
   - **Suspend the web service first**, so no deploy runs `migrate` against a
     half-restored database. Then `DROP SCHEMA public CASCADE; CREATE SCHEMA
     public;`, `pg_restore --no-owner --no-acl --exit-on-error`, both through
     `docker exec -i villacollective-db …` (client matches the dump's version).
   - **Verify before deploying:** image / property / `django_migrations` counts
     must match local. The migration count must equal
     `showmigrations --plan | wc -l` from a *clean* venv (78 at `bea09ed6`).
   - **Trap — a damaged local venv.** On 2026-07-08 something deleted Django's
     own contrib migrations inside `django_res/.venv` and regenerated one
     `0001_initial` per app, so the local DB recorded 64 migrations where stock
     Django has 78. The first restore then failed on staging at
     `contenttypes.0002` ("column name does not exist"). Fix: `uv sync
     --reinstall-package django`, confirm the contrib schema matches a
     stock-migrated scratch DB, `migrate --fake`, re-dump. Any venv older than
     that date may carry the same damage.
   - Resume the service, deploy (expect "No migrations to apply"),
     `createsuperuser`.
   - Why not run the loaders straight at Render: `loadlegacy --all` is a
     one-shot that refuses a non-empty DB, and thousands of round-trips over
     the internet make a dropped connection likely. A restore is minutes and
     ships exactly the database that reconciled.
   - **`seed_dev` must never run on staging again** after this: legacy data
     replaces seed data, they do not mix.
5. ✅ **Upload the legacy images to staging** — done 2026-09-21, 1 h 25 min
   from the operator's laptop (~210 files/min), `uploaded 18232`, `missing 0`.
   The repeatable recipe:
   ```bash
   cd django_res
   export DJANGO_SETTINGS_MODULE=villacollective.settings.staging
   export AWS_PROFILE=villacollective-dev
   # dummies for the vars staging.py fails fast on:
   export DJANGO_SECRET_KEY=local-import-only FERNET_KEYS=local-import-only \
          FLYWIRE_WEBHOOK_SECRET=x STRIPE_WEBHOOK_SECRET=x \
          DOCUMENTS_S3_BUCKET=villacollective-documents \
          EMAIL_RECIPIENT_ALLOWLIST=you@example.com
   uv run python manage.py import_legacy_images \
       --source ~/villacollective-legacy/PropertyImages --dry-run   # expect missing 0
   caffeinate -s uv run python manage.py import_legacy_images \
       --source ~/villacollective-legacy/PropertyImages
   ```
   - **Leave `DATABASE_URL` at the local, legacy-loaded database.** The command
     does not scan the folder: it reads the `properties/legacy/…` image rows
     (and each property's `legacy_id`) from the database, finds
     `<source>/<legacy_id>/<filename>` and uploads it to the row's key. The
     settings module picks the *bucket*; the database only supplies the list of
     keys, and is never written. Staging is a restore of the local database, so
     the keys are identical — which also means this step does not depend on
     step 4 and needs no access to Render's database.
   - `AWS_PROFILE` (the CLI user) is fine *from the laptop*; the rule is only
     that those keys never go to Render.
   - Idempotent — interrupt and re-run freely. **Keep the lid open:**
     `caffeinate -s` stops idle sleep, not lid-close sleep.
   - stdout is block-buffered when redirected to a file, so the `uploaded n/N`
     lines appear only at exit; watch progress with
     `aws s3 ls s3://villacollective-images/staging/properties/legacy/ --summarize`.
6. ✅ **Staging reset rule fixed** (2026-09-21, GAP-012 decision A and runbook
   updated). Wiping `staging/` whole would now delete 11 GB of legacy photos;
   the rule is
   `aws s3 rm --recursive s3://villacollective-images/staging/ --exclude "properties/legacy/*"`.
7. **Smoke test staging:** a migrated villa's gallery renders; a fresh upload
   works; deleting a fresh image removes its object; a legacy `image_url` is an
   absolute `https://villacollective-images.s3.eu-central-1.amazonaws.com/staging/properties/legacy/…`.

## Step 3 — real personal data on staging (blocking)

A legacy load puts real customers, owners and contracts on staging. Checked in
the code 2026-09-21:

- **Email:** safe. `staging.py` refuses to boot without
  `EMAIL_RECIPIENT_ALLOWLIST`; nothing reaches a real guest.
- **Zoho push:** off *if* the `ZOHO_FLOW_WEBHOOK_*` env vars are unset (an
  empty URL disables the kind). `render.yaml` does not declare them, but the
  Render dashboard can — **check the dashboard** before loading. With them set,
  saving a migrated record would push real people into whatever CRM they point
  at.
- **Background sweeps:** none. Staging runs Celery eagerly with no worker or
  beat, so no periodic job touches the loaded rows.
- **Payments:** inbound webhooks only; confirm the Stripe/Flywire keys on
  staging are test-mode.
- **Not checked, needs a human:** who holds staging logins, and whether the
  `.onrender.com` URL is known outside the team. Loaded staff users arrive with
  their legacy accounts — decide whether to keep, reset or deactivate them.

## After staging: production (not this ticket — CUTOVER §8)

- Create `villacollective-app-prod` (GAP-012 §Infrastructure has the policy).
- Fill the production bucket **server-side** rather than uploading 11 GB again:
  `aws s3 sync s3://villacollective-images/staging/properties/legacy/ s3://villacollective-images-prod/production/properties/legacy/`,
  then prove it with `import_legacy_images --dry-run` under production settings
  (expect `uploaded 0`, `skipped 18232`).
- The production service's **first deploy must come after that**, and it needs
  `DOCUMENTS_S3_BUCKET=villacollective-documents-prod`.

## Acceptance

- Staging shows legacy villas, enquiries and quotes with their photos; no
  legacy `image_url` 404s.
- Staging runs on `villacollective-app-staging` keys; the CLI user's keys are
  on no Render service.
- `reconcile_legacy` exited 0 on the database that was restored.
- The step-3 checks are written down with their answers.
- The staging reset rule excludes `properties/legacy/`.

## Dependencies

- **GAP-012** — storage, buckets, IAM, the two commands. Closes when this
  ticket's steps 2 and 5 and the production import are done.
- **CUTOVER.md** — the loader runbook this rehearses.
- Unblocks **GAP-106** (website push ships image URLs) and **CHECK-003**'s
  hero-image URL on real data.
