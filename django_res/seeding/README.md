# Dev data seeding

`seed_dev` generates realistic dev/staging data by composing the per-app
`factory-boy` factories. This file is the detailed reference; the short rules
that agents must not violate live in `django_res/CLAUDE.md`.

## `seed_dev` command

    ./manage.py seed_dev [--scale small|medium|large] [--properties N]
                         [--bookings N] [--seed S] [--i-understand]

It is **additive** — every run appends a fresh batch and never truncates. The
transactional graph (Enquiry → Quotation → Booking → Payment) is built through
the real service layer (`QuotationService`, `BookingService`,
`PaymentScheduler`, `SecurityDepositService`), so statuses, events, holds and
pricing snapshots are production-faithful; a fraction of bookings are walked
down the state machine for status variety.

**Production block.** Guarded by `settings.SEED_DEV_ALLOWED` (False in
`base`/production, True in `dev`/`test`/`staging`). `--i-understand` documents
intent only — it does **not** bypass the production block.

Reference: `seeding/management/commands/seed_dev.py`, `properties/factories.py`,
and the per-app `tests/test_factories.py`.

## Dense, varied calendars (mixed / chaos)

Outside `happy`, the `bookings` stage spreads its budget across **density
tiers** instead of a flat round-robin: a few *packed* villas (booked across the
full ±`booking_date_spread_days` year, incl. back-to-back changeover pairs),
more *busy*, many *light*, and some *empty* villas. Empty villas read as
new/unlisted and double as candidates for the `property_lifecycle`
draft/archive pass.

`--bookings` keeps its exact meaning — it is the total budget, just distributed
by tier weight — and the default `--scale` budgets are generous (`small` 30 /
`medium` 110 / `large` 400) so a default run looks busy. The profile sets
`dense_calendar` plus `changeover_times` (`10:00`/`16:00`, written onto
`PropertySettings` so adjacent stays render an AM/PM changeover day); `happy`
leaves both off and keeps the legacy sparse round-robin byte-for-byte. The
dense path and the legacy path share one per-stay builder, `create_one_booking`.

Note: nothing seeds a `BOOKING_DEPOSIT_PENDING` hold — that calendar state has
no backend producer (the frontend renders a legend entry for it, but it is
currently dead).

## Factory conventions (mirror these in new factories)

- **Cross-run uniqueness.** `factory.Sequence` is an in-process counter, *not*
  unique across runs. Unique fields combine the per-process `RUN_TOKEN` (a uuid
  defined in `core/factories.py`, imported *down* by every app's factories)
  with the sequence, so additive runs never collide on a unique constraint
  (slug, email, phone).
- **Respect seeded/canonical rows.** Factories for migration-seeded or
  canonical models (`CountryFactory`, `CurrencyFactory`,
  `PropertyCategoryFactory`, `TermsVersionFactory`) use `django_get_or_create`
  so they reuse the seeded row instead of fighting its unique constraint — the
  analogue of the `get_or_create` fixture rule in `django_res/CLAUDE.md`.

## Villa image pool — manifest-driven seed imagery

`seed_dev` draws property imagery *and* property identity from a committed pool
of villa images under `core/seed_data/villa_images/`, so dev/staging
catalogue/detail screens render real villas instead of grey 1×1 placeholders.
`manifest.yaml` is the single source of truth: one entry per villa with `slug`,
`display_name`, `location_tag`, `country_iso2`, `style_anchor`, and per-kind
`prompts`. Each entry owns a subdirectory of `hero.jpg` / `interior.jpg` /
`exterior.jpg` / `gallery.jpg` (no floor plans — the model produces poor ones;
`FLOOR_PLAN` falls back to the 1×1 placeholder).

How it wires together (mirror this if you extend it):

- `properties.factories.villa_manifest()` returns the manifest entries that
  have a `hero.jpg` on disk. The `properties` seed stage cycles that list,
  **exhausting every villa before any repeat**, and builds each property's
  `display_name` / `region` / `country` (loud `Country.objects.get` on the
  seeded ISO row) / description from the entry.
- `PropertyFactory` writes the HERO via the `children__villa` post-gen kwarg;
  the `gallery` stage writes the non-HERO images from the *same* villa, tracked
  on `SeedContext.property_villa` (pk → slug). Image bytes are memoised per
  `(slug, kind)`. Missing files / non-manifest properties fall back to the 1×1
  placeholder, so a checkout without the pool (and the
  `tests/test_factories.py` cases) still works — they `pytest.skip` when the
  pool is absent.

Regenerate / expand the pool with the one-off command (writes the working tree,
not the DB; **not** gated by `SEED_DEV_ALLOWED`):

    ./manage.py generate_seed_images [--only <slug>] [--kind <hero|interior|
        exterior|gallery>] [--quality <low|medium|high|auto>] [--dry-run] [--force]

It builds each image from the manifest via OpenAI `gpt-image-1` (`1536×1024`,
3:2), re-encodes to ~1200 px JPEG q80 with Pillow, is idempotent (skips
existing files unless `--force`), and refuses to run without `OPEN_AI_API_KEY`.
That key (and any local secret) is read from the **repo-root `.env`**, loaded by
`villacollective/settings/base.py` via
`environ.Env.read_env(BASE_DIR.parent / ".env")`.

Reference: `core/management/commands/generate_seed_images.py`,
`core/seed_data/villa_images/{manifest.yaml,README.md}`,
`seeding/stages/{properties,gallery}.py`.
