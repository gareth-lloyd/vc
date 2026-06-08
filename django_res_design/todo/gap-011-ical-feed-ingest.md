# GAP-011 — iCal feed ingest from owners

**Severity:** gap (designed-but-unbuilt; **explicitly deferred past v1**).

**Status:** ⬜ deferred — tracker. No model or workflow in v1. This ticket is
the single canonical home for the feature; `06-availability.md`,
`08-integrations.md`, and `10-decisions.md` now point here instead of each
carrying their own copy.

**Source:** scoping-session **2026-05-26** with the site owner; **re-emphasised
in the 2026-06-08 demo** ("incredibly useful", "a game changer", "a big problem
in the business… very hard to keep [availability] up to date"). Recognised as
one of the highest-value v2 force-multipliers. Previously specced in three
places (now consolidated):
- `06-availability.md` §"Out of scope (future)" — availability-side framing.
- `08-integrations.md` §"Out of scope" — integration-side framing.
- `10-decisions.md` §"Deferred" — the canonical deferral registry row.

## Problem

A meaningful share of the catalogue already publishes public iCal feeds
(Airbnb / Vrbo / Booking.com / Google-calendar exports and the like). Today the
legacy team **mirrors them manually through shared Outlook calendars** — pure
recurring toil and a source of stale availability. Pulling the feeds directly
into the availability surface removes the manual mirror and keeps owner-blocked
dates current automatically.

> **Volume — confirm before scoping.** The 2026-05-26 note recorded "~30
> villas"; the 2026-06-08 demo said "**about 30% of** villas". Count vs.
> proportion are materially different (they only coincide if the catalogue is
> ~100 villas) and feed directly into poller-throughput and cadence sizing —
> reconcile against the real catalogue size before scoping. The demo also
> confirmed the **capability-URL model** end-to-end from the owner's side: an
> owner keeps a per-villa calendar and "shares a link" the team stores and
> re-reads — exactly the secret-token-in-URL shape handled in *Postponed
> decisions* §2.

> **Adjacent opportunity (not this ticket, same pain).** iCal ingest only covers
> owners who *publish* a feed. For the rest, the owner named a competitor pattern
> worth pursuing in parallel: **owners emailed a one-click link to update their
> own availability** on a cadence. Same root pain — "time spent chasing owners
> for availability updates is time when clients are shopping around losing
> interest." That pattern is owner-portal / self-serve-availability work
> (deferred; `10-decisions.md` owner-portal row + The Collectionist follow-up),
> complementary to this feed-ingest ticket. Neither is M1.

This is **not in MVP**. It is captured so the v1 model stays amenable to the
extension and so the agreed shape isn't re-litigated when it lands.

## Industry context (how these feeds actually behave)

iCal export/import is the lowest-common-denominator availability sync across the
whole short-term-rental world — Airbnb, Vrbo, Booking.com, Google Calendar, and
the PMSs (Lodgify, Hostaway, …) all expose a per-listing `.ics` export and poll
each other's. There is **no push/webhook** — you re-fetch a flat file on a
schedule. The design sits firmly in this mainstream, but the mainstream carries
well-known sharp edges (captured as postponed decisions below). The single most
important simplifying choice is the **semantic collapse**: *every* event in a
feed becomes one `BookingHold(reason=OWNER_BLOCK)` — VC does not care whether a
date is "booked on Airbnb" or "owner blocked", only that it is not bookable
through VC. That collapse is what lets a single generic parser serve all sources.

## Proposed fix (the agreed shape)

When this lands, the natural shape is:

1. **Feeds are a first-class child entity, not a column.** A villa listed on
   Airbnb + Vrbo + Booking.com has **several** export URLs, so the model is a
   new child table — call it `PropertyCalendarFeed` — with **N feeds per
   property** (FK to `Property`; see *Postponed decisions* §1 for the exact
   owner linkage and fields). This is the design-significant change from the
   prior "a URL field on `PropertySettings`" framing, which assumed one feed.

2. **One generic poller + per-source profiles (no per-villa, no per-OTA code
   paths).** A single task iterates active feeds and runs one generic iCal
   parser. Source-specific quirks (DTEND convention, UID strategy, `webcal://`
   normalization, `STATUS:TENTATIVE` handling, optional `SUMMARY`→meaning map)
   live in a small **declarative profile per provider**, not in branching code.
   See *Per-source profiles vs code paths* below for the rationale.

3. **Write target** — one `BookingHold(reason=OWNER_BLOCK, expires_at=NULL)` row
   per (coalesced) event, **idempotent on a composite key**, not on the raw
   iCal `UID` alone (UIDs are not reliably stable across OTA exports — see §4).

4. **Integration state** — a new `SyncProvider.ICAL` value on
   `integrations.SyncRecord`, one record per feed, reusing its `external_id`
   field as the per-feed idempotency anchor.

5. **Staff awareness notification.** Imported blocks must notify staff for
   awareness, the same way owner-created blocks do — they change sellable
   availability with no VC operator in the loop. Reuse the existing `comms`
   signal→`EmailService` pattern (cf. `hold_expired` → email to the creating
   agent, `10-decisions.md` "Hold auto-expiry"), but with two iCal-specific
   shapes (see *Postponed decisions* §9): **(a)** routine new/released blocks are
   **batched into a per-poll digest** — a poll can touch many villas every few
   hours, so per-row email would be spam; **(b)** an imported block that
   **overlaps an existing live VC booking is a conflict alert, not routine
   awareness** (see corollary below).

The core availability model does **not** need to change — owner blocks are
already `BookingHold` rows enforced by the existing exclude constraint.

> **Conflict-detection corollary.** The two exclude constraints are separate
> (assumption #3): `bookinghold_no_overlap_live` stops hold-vs-hold overlap and
> `booking_no_overlap_blocking` stops booking-vs-booking overlap — but **nothing
> stops a new `BookingHold` from overlapping an existing `Booking`**. That is
> exactly the dangerous case: the villa was sold on Airbnb for dates VC has
> already booked. So iCal ingest doubles as a **double-booking detector** — when
> an imported event overlaps a live VC `Booking`, escalate to a high-priority
> staff conflict alert rather than the routine digest (write-vs-only-alert is
> open — §9).

## Assumptions tested against code (2026-06-08)

Each load-bearing claim in the prior prose was verified against `django_res/`.
Results — three confirmed, two needed correcting before implementation:

| # | Assumption | Verdict | Evidence |
|---|---|---|---|
| 1 | `BookingHold.reason` has an `OWNER_BLOCK` choice | ✅ **true** | `reservations/enums.py:127` — `BookingHoldReason` = `QUOTATION_OPEN`, `OWNER_BLOCK`, `MAINTENANCE`, `MANUAL`. (No `STOP_SALE` value exists — it's a *display* label mapped onto `OWNER_BLOCK`, not a stored reason; see `10-decisions.md` "Stop Sale".) |
| 2 | No-expiry holds are safe from the reaper | ✅ **true** | `BookingHold.expires_at` is `null=True` (`reservations/models/booking.py:716`); `tasks.expire_holds` filters `expires_at__isnull=False` (`reservations/tasks.py:30`), so `NULL` (owner/maintenance) holds are never reaped. iCal blocks should be created with `expires_at=NULL`. |
| 3 | iCal blocks slot into the same `EXCLUDE` constraint with no model change | ⚠️ **needs correcting** | There is **no single shared constraint**. `BookingHold` has its own — `bookinghold_no_overlap_live` `WHERE (released_at IS NULL)` (`migrations/0002`); `Booking` has a separate one keyed on status (`migrations/0007`). The relevant point still holds — an `OWNER_BLOCK` hold *does* block overlapping bookings — but "they participate in the same constraint" was wrong. **Consequence:** overlapping events for one villa-range (including the *same* booking arriving via two feeds — see §6) will violate `bookinghold_no_overlap_live`. The poller must coalesce overlaps **across all of a property's feeds**, not naively insert one row per event. |
| 4 | `SyncRecord` can carry `provider=ICAL` + a per-feed idempotency key | ✅ **true, ready** | `integrations/enums.py:12` `SyncProvider` = `ZOHO_CRM`, `FLYWIRE`, `WORDPRESS_SITE`, `LEGACY_DOTNET` (add `ICAL`). `SyncRecord` has `external_id` (db-indexed) + `UniqueConstraint(provider, external_id) WHERE external_id > ''` (`models/sync_record.py:50`), and a `GenericForeignKey` (`target`) that can point at the feed or the `BookingHold`. |
| 5 | A per-villa URL belongs on `PropertySettings` / `PropertyContactAssignment` | ⚠️ **superseded by multi-feed** | Both models exist (`properties/models/settings.py:32`, `properties/models/contacts.py:10`) and `PropertyContactAssignment.role` has `OWNER` (`accounts/enums.py:40`), but **a single URL column can't hold N feeds**. The feed becomes its own child model (Proposed fix §1); see *Postponed decisions* §1 for its owner linkage. |

**Greenfield confirmation:** no existing iCal code anywhere — no `icalendar`
in `pyproject.toml`, no `.ics` parsing, no `ICAL` provider. Blank slate, so no
reuse/refactor constraints. (Prefer an off-the-shelf parser — `icalendar` /
`ics.py` — over hand-rolling RFC 5545, per the project's library-first rule.)

## Feed format & semantics realities (general-knowledge caveats)

These are not project-specific but they are where iCal integrations actually
break in production. They drive the postponed decisions below.

- **Capability-URL auth, *usually* but not always.** "Public iCal feed" normally
  means a plain `GET` with **no login / header / OAuth**, but an unguessable
  secret token baked into the URL (`airbnb.com/calendar/ical/<id>.ics?s=<tok>`,
  Google `…/private-<tok>/basic.ics`, Vrbo `/icalendar/<tok>.ics`). The token
  *is* the credential. **But** some feeds are genuinely tokenless-public
  (a public Google calendar address, a small-PMS webcal) — so treat the URL as
  secret by default, without assuming every URL carries a token. → §2.
- **`webcal://` is not a separate protocol** — it's `https://` with a scheme
  swap to trigger calendar-app subscription. Normalize `webcal://` → `https://`
  (and upgrade bare `http://` where the host supports it).
- **UIDs are not reliably stable or globally unique** across OTA exports. Google
  is stable; Airbnb mostly; others regenerate UIDs, reuse a generic UID, or
  collide across listings. UID-keyed idempotency is the right instinct but needs
  a composite fallback. → §4.
- **`DTEND` off-by-one is the classic iCal bug.** All-day events use
  `VALUE=DATE` with `DTEND` = checkout **morning** (exclusive) — which maps
  *cleanly* onto our half-open `[date_from, date_to)` range model. But some
  feeds emit `DTEND` as the inclusive last night. A single off-by-one here
  causes more real double-bookings than any auth issue. → §5.
- **Eventual consistency, not real-time.** OTA exports lag (Airbnb's can be an
  hour+), and providers rate-limit polling. Double-bookings in the sync gap are
  an accepted industry risk; the cadence decision must own this latency. → §3.
- **Timezone coupling is weaker than first assumed.** Blocks are almost always
  all-day `DATE` values (floating, no TZ), so `fg-008-property-timezone` mostly
  does *not* bear on the block dates themselves — the DTEND off-by-one is the
  real date hazard, not timezone.

## Per-source profiles vs code paths (decided)

**Per-villa code paths: no.** Won't scale (30 villas and growing) and violates
KISS — villa-specific behaviour is *data/config*, never branching code.

**Per-calendar-type code paths: no — use declarative profiles instead.** Because
of the semantic collapse (every event → `OWNER_BLOCK`), one generic parser is
correct for all sources; they differ only in *data quirks*, and the wire
protocol is identical ("HTTP GET an `.ics`"). So the shape is **one poller + one
parser + a small declarative profile per `SyncProvider`** describing: DTEND
convention, UID-stability strategy, `webcal`/`http` normalization,
`STATUS:TENTATIVE` handling, and (optionally) a `SUMMARY`→meaning map. This is
"config, not a subclass per vendor", and it composes naturally with multi-feed
(you iterate feeds, each carrying its profile). Escalate to a real
strategy/subclass **only** if a source proves un-handleable declaratively. The
one place genuine branching might later be justified is `SUMMARY`-classification
— *only if* the product wants the calendar to distinguish "booked elsewhere"
from "owner blocked" (the Stop Sale vocabulary). That is a product decision, not
a technical necessity, and stays deferred.

## Postponed decisions

Open choices to settle at implementation time:

1. **Feed model shape & owner linkage.** A new `PropertyCalendarFeed` child
   (N per property): minimally `property` FK, `url` (secret), `provider`/source
   type, `label`, `is_active`, `last_polled_at`, `last_status`. Open: does it
   also FK `PropertyContactAssignment` (to attribute a feed to a specific
   owner), or just `Property`? Leaning property-scoped with an optional
   owner FK, since a villa's feeds outlive owner churn.

2. **Feed authentication / the secret-URL hazard.** Investigated 2026-06-08:
   the legacy prod dump contains **no iCal URLs and no column to hold one** —
   they live only in the team's Outlook, so they could not be fetch-tested
   here; confirm the auth model against the real ~30 URLs once ops exports them.
   Expected model is the capability URL above. Two consequences:
   - **Poller needs no auth machinery** — just an HTTP GET (after `webcal`/http
     normalization). Good.
   - **The stored URL is a credential.** It exposes the owner's full booking
     calendar to anyone with DB-read / API / log access. The field must be
     treated as a secret (excluded from API responses, owner UI, and logs), and
     the design must handle owner-rotated/revoked tokens (feed starts 404ing or
     returns a different calendar).

3. **Scheduling substrate + cadence.** ✅ Resolved. Celery is now wired
   (broker + worker + beat — see `django_res/CLAUDE.md` §"Background tasks").
   `reservations.tasks.ingest_ical_feeds` is a real `@shared_task` and is
   registered in `CELERY_BEAT_SCHEDULE` (`settings/base.py`) at a 15-minute
   cadence; the `manage.py ingest_ical` command remains as a manual escape
   hatch. The cadence owns the eventual-consistency reality (poll lag; accept a
   sync-gap double-booking window the conflict alert surfaces).

4. **Idempotency key under unstable UIDs.** Upsert holds on a **composite key**
   — e.g. `hash(UID + DTSTART + DTEND + SUMMARY)` scoped per `(property,
   feed)` — rather than raw `UID`, because OTA UIDs drift/collide. Define the
   exact key and how it survives an owner editing an event in place.

5. **DTEND normalization.** Per-profile flag for exclusive vs inclusive `DTEND`,
   normalized to our half-open `[date_from, date_to)` before writing. This is
   the highest-risk correctness detail; it needs explicit per-source tests.

6. **Cross-feed overlap coalescing (from assumption #3).** The same real-world
   block can appear in **multiple feeds** for one villa (owner cross-synced
   Airbnb↔Vrbo), and overlapping events trip `bookinghold_no_overlap_live`. The
   poller must merge overlapping/adjacent ranges **across all of a property's
   feeds** before writing, and define how the composite key (§4) maps onto a
   merged range.

7. **Stale-event reconciliation.** Feeds don't send deletions — when an event
   disappears (owner cancelled), the corresponding `OWNER_BLOCK` hold must be
   released. Needs a "holds present in DB but absent from this poll → release"
   sweep, scoped per `(property, feed)` so one feed's poll doesn't release
   another feed's holds.

8. **`SUMMARY`/`STATUS` classification (optional, product-gated).** Whether to
   parse `SUMMARY`/`STATUS:TENTATIVE` to distinguish booked-elsewhere vs
   owner-block vs tentative for *display* (Stop Sale vocabulary). Out of scope
   unless the product asks; if it does, it lives in the per-source profile's
   `SUMMARY`→meaning map, not in new code paths.

9. **Staff notification shape (Proposed fix §5).** Settle: **(a) digest
   granularity** — one email per poll-run, or one per property with changes?
   (Per-run digest avoids spam; per-property is more actionable.) **(b) recipient
   set** — owner-created blocks notify a specific agent; an automated poll has no
   "creating agent", so who? (ops distro / the property's assigned agent via
   `PropertyContactAssignment(role=AGENT)` / a settings-driven list.) **(c)
   conflict handling** — when an imported event overlaps a live VC `Booking`, do
   we still write the overlapping hold (so the calendar shows the clash) and
   raise a high-priority alert, or skip the write and alert only? Leaning
   write-and-alert so the conflict is visible in the availability surface, but it
   needs a product call. **(d)** reuse `comms.EmailTemplate` + a new signal
   (e.g. `ical_blocks_imported` / `ical_conflict_detected`), consistent with the
   `hold_expired` pattern.

## Acceptance (when it leaves deferred)

- `SyncProvider.ICAL` added; `SyncRecord` tracks one record per feed.
- New `PropertyCalendarFeed` child model supporting **N feeds per property**;
  `url` treated as a secret (not serialized to owner-facing APIs; not logged).
- A poller (Celery task or management command) pulls each active feed via a
  single generic parser + per-source profile, normalizes `webcal`/`DTEND`,
  upserts `BookingHold(reason=OWNER_BLOCK, expires_at=NULL)` rows on the
  composite key, **coalesces overlaps across the property's feeds**, and
  releases holds for events that vanished from a feed.
- Blocks show as unavailable in `AvailabilityService.calendar()` and catalogue
  search with no change to the availability model.
- Staff are notified of imported blocks for awareness (batched per-poll digest),
  and an imported event overlapping a live VC `Booking` raises a high-priority
  conflict alert — via the `comms` signal→`EmailService` pattern.
- Tests: idempotent re-poll (no duplicate holds); UID-drift handled by the
  composite key; exclusive vs inclusive `DTEND` per profile (off-by-one);
  cross-feed overlap coalescing; stale event → hold released (and *only* that
  feed's holds); `webcal://` normalization; malformed/404/empty feed handled
  without crashing the run; awareness digest fires once per poll (not per row);
  booking-overlap raises the conflict alert.

## Dependencies

- ~~**Blocked by** the Celery-vs-cron decision (postponed §3) for the
  scheduling half~~ — unblocked: Celery is wired and `ingest_ical_feeds` is
  beat-scheduled (§3). The data half (`SyncProvider.ICAL`, `PropertyCalendarFeed`)
  already landed.
- **Related:** `06-availability.md` (owner-block semantics, exclude
  constraints), `08-integrations.md` (`SyncRecord` framework), `10-comms.md` /
  `10-decisions.md` "Hold auto-expiry" (the signal→`EmailService` pattern reused
  for staff notification, Proposed fix §5). `fg-008` is only weakly related —
  blocks are all-day `DATE` values, so property timezone mostly doesn't bear on
  the block dates (the DTEND off-by-one does).
