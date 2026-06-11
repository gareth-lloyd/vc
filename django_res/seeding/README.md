# Dev data seeding

`seed_dev` generates realistic dev/staging data by composing the per-app
`factory-boy` factories. This file is the detailed reference; the short rules
that agents must not violate live in `django_res/CLAUDE.md`.

## `seed_dev` command

    ./manage.py seed_dev [--scale small|medium|large] [--properties N]
                         [--bookings N] [--seed S] [--no-dashboard-activity]
                         [--i-understand]

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

## Dashboard activity (all profiles)

The dense calendar almost never lands a stay exactly on today, never *rests* a
booking at `AWAITING_BALANCE`, and never leaves an enquiry `NEW` — exactly the
slices the staff dashboard reads. The `dashboard_activity` stage therefore
guarantees five cohorts after every run, in **every profile** including
`happy` (base counts, × `dashboard` scale multiplier — 1/2/3 for
small/medium/large):

| Cohort | Count | Resting status | Feeds |
|---|---|---|---|
| Arrivals today | 5 | `BALANCE_PAID` | staff "Arrivals today" hero |
| Departures today | 3 | `BALANCE_PAID` | staff "Check-outs today" |
| Awaiting balance | 4 | `AWAITING_BALANCE` | staff "Awaiting balance" |
| NEW enquiries | 5 | `NEW` | staff "New enquiries" |
| Owner upcoming | ≤4 | `DEPOSIT_PAID`, next 30 days | owner portal "Upcoming arrivals" |

Placement rules worth knowing:

- "Today" is the **UTC calendar date** (`seeding.context.utc_today`), matching
  how both dashboards compute it — never the server-local date.
- Departures rest `BALANCE_PAID`, not `CHECKED_IN`: the daily `auto_check_out`
  beat task sweeps `CHECKED_IN` stays with `date_to <= today` into terminal
  `CHECKED_OUT`, which the dashboard hides — the tile would die at the next
  beat tick on staging.
- Candidates are searched **busy-first** (villas with existing stays before
  empty ones), so the deliberately-empty density tier is consumed last. When
  no existing villa is free for a window, a **showcase villa** is minted —
  manifest-styled (real name/region/hero) with changeover times, registered
  on the run's property list, and reused for later windows — so
  `--properties N` is a *floor*, not an exact bound, and additive reruns can
  accrete a few extra villas (the stage logs `seed.dashboard_showcase_minted`
  with the count).
- The stage runs after `refunds`, whose goodwill cohort queries `BALANCE_PAID`
  bookings DB-wide — ordering keeps the curated arrivals refund-free.
- Today-anchored stays are 3 nights and the departure/arrival windows abut at
  today, so a reused villa renders a same-day AM/PM changeover where
  changeover times are set (mixed/chaos).
- The owner-upcoming cohort is opportunistic and stays on the villas granted to
  the seeded owner org — a minted showcase villa has no grant and would not
  show on the owner dashboard.
- **Today-anchored data is stale tomorrow.** A demo/staging DB should be
  reseeded (additively) on the day it's shown.

`--no-dashboard-activity` skips the stage entirely — use it where the exact
legacy output matters (e.g. exact booking-count tests).

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

`seed_dev` draws property imagery, location, and description from a committed
pool of villa images under `core/seed_data/villa_images/`, so dev/staging
catalogue/detail screens render real villas instead of grey 1×1 placeholders.
`manifest.yaml` is the single source of truth: one entry per villa with `slug`,
`location_tag`, `country_iso2`, `style_anchor`, and per-kind `prompts` (plus a
`display_name` used only as image-generation context). Property *names* do not
come from the manifest — `properties.factories.villa_name` combines a
deterministic component menu into 630 unique names, so seeded names never
repeat the way the 20-entry manifest would. Each entry owns a subdirectory of `hero.jpg` / `interior.jpg` /
`exterior.jpg` / `gallery.jpg` (no floor plans — the model produces poor ones,
so the gallery stage skips `FLOOR_PLAN` entirely rather than seed a 1×1
placeholder).

How it wires together (mirror this if you extend it):

- `properties.factories.villa_manifest()` returns the manifest entries that
  have a `hero.jpg` on disk. The `properties` seed stage cycles that list,
  **exhausting every villa before any repeat**, and builds each property's
  `region` / `country` (loud `Country.objects.get` on the seeded ISO row) /
  description from the entry.
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
