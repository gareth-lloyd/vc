# GAP-120 — Legacy data + legacy images on staging

**Severity:** gap (ops programme — almost no code; the tools all exist).

**Status:** ⬜ filed 2026-09-21. Everything it needs is built and on local
`main` (unpushed). This ticket is the ordered checklist for getting a
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
| Local `main` | ⬜ ~160 commits ahead of `origin/main`, unpushed. Pushing deploys **staging only** (`render.yaml` → `settings.staging`); no production service exists yet |
| Staging database | `seed_dev` demo data, no legacy rows |

## Next steps, in order

1. **Push `main`.** Redeploys staging; `preDeployCommand` runs `migrate`. If it
   stops on `rateplan_one_active_per_regime`, see the pre-step at the top of
   CUTOVER §4 — moot if step 4 replaces the database anyway, in which case
   reset the staging DB first and push onto an empty one.
2. **Swap staging's AWS keys** in Render to `villacollective-app-staging`.
   Verify: upload an image in the staging SPA, download a contract. Then the
   `villacollective-cli` keys are off Render for good.
3. **Pre-flight the personal-data question (blocking — see below).**
4. **Load the legacy data: build locally, restore to staging.**
   - Fresh empty local DB → `migrate` → `loadlegacy --all` against the local
     `res-db` dump (CUTOVER §0–4) → `reconcile_legacy` exits 0 (§5) → the §6
     late writes that apply to a fresh load.
   - `pg_dump -Fc` that DB; reset the staging DB; `pg_restore` into Render's
     external connection string; create the staff logins.
   - Why not run the loaders straight at Render: `loadlegacy --all` is a
     one-shot that refuses a non-empty DB, and thousands of round-trips over
     the internet make a dropped connection likely — which leaves a
     half-loaded one-shot. A restore is minutes and ships exactly the database
     that reconciled.
   - **`seed_dev` must never run on staging again** after this: legacy data
     replaces seed data, they do not mix.
5. **Upload the legacy images to staging** from the operator's machine:
   ```bash
   export DJANGO_SETTINGS_MODULE=villacollective.settings.staging
   export DATABASE_URL=<Render staging external connection string>
   export AWS_ACCESS_KEY_ID=… AWS_SECRET_ACCESS_KEY=…   # villacollective-app-staging
   # plus the other vars staging.py fails fast on (dummy values are fine)
   uv run python manage.py import_legacy_images \
       --source ~/villacollective-legacy/PropertyImages --dry-run   # expect missing 0
   caffeinate -s uv run python manage.py import_legacy_images \
       --source ~/villacollective-legacy/PropertyImages
   ```
   ~11 GB up; idempotent, so interrupt and re-run freely. **Keep the laptop
   open** — the fetch lost ~3 h to lid-close sleep. Lands in
   `villacollective-images/staging/properties/legacy/` (~$0.30/month).
6. **Fix the staging reset rule.** GAP-012 decision A says "wipe `staging/`
   recursively on a DB reset". After step 5 that deletes 11 GB of legacy
   photos. New rule:
   `aws s3 rm --recursive s3://villacollective-images/staging/ --exclude "properties/legacy/*"`.
   Update GAP-012 when this step is reached (left as-is until then, because
   today the old rule is still correct).
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
