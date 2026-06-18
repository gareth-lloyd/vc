# GAP-034 — Sales-view calendar-source indicator: iCal badge + owner calendar link

- **Severity:** Gap (sales-team UX; builds on the shipped iCal feed model)
- **Source:** owner Loom walkthrough 2026-06-17 (availability section, 2:25–3:01):
  "we have a link here — this is for villas which have availability online, but
  not iCal… it allows a salesperson to very quickly open up the webpage so they
  can check their online calendar. Obviously if there's iCal, then we want it to
  state iCal, so they understand that is the latest [availability] from the
  owner."
- **Files:** `properties/models/calendar_feed.py` (`PropertyCalendarFeed` — already
  shipped), a new browsable calendar-link field on `Property`/`PropertySettings`
  (confirmed absent today — no online-calendar URL field exists on `Property`; the
  only `*_description`/URL-ish field nearby is `Room.website_description`, a
  per-room marketing field, unrelated), property serializer +
  `frontend/src/features/availability/{TimelineGrid.tsx,api.ts,schemas.ts}`,
  `frontend/src/features/properties/tabs/AvailabilityTab.tsx`.

## Problem

Two distinct "the owner's availability lives elsewhere" cases need surfacing to
sales:

1. **iCal-synced villas** — VC already auto-ingests the owner's iCal feed
   (`PropertyCalendarFeed`, see GAP-011). Sales should see an **"iCal" badge** so
   they know the on-screen availability is the latest auto-synced source from the
   owner.
2. **Online-but-not-iCal villas** — the owner keeps an online calendar webpage
   that VC does *not* ingest. Sales need a **quick link** to open that webpage and
   eyeball the owner's calendar.

Today neither is surfaced in the sales timeline.

## Proposed fix

- **iCal badge.** Show an "iCal" indicator in the sales timeline (and property
  view) when the property has active `PropertyCalendarFeed` rows. Expose a
  boolean/`has_active_ical_feed`-style flag on the property serializer — **do not
  expose the feed `url`**, which GAP-011 treats as a secret credential.
- **Calendar link.** No "online calendar link" field exists on `Property` today
  (verified — `Room.website_description` is a per-room marketing field, not a
  calendar URL), so add a browsable `calendar_url` (distinct from the secret iCal
  feed `url`) and surface it as a quick link in the sales view.
- **Optionally** surface feed health (`last_polled_at` / `last_status`), currently
  backend-only, as part of the badge tooltip.

## Precedence (state explicitly)

A property may have both. **Active iCal feed → "iCal" badge wins** (it's the
latest-from-owner auto-synced source); otherwise show the `calendar_url` link.

## Acceptance

- Properties with an active `PropertyCalendarFeed` show an "iCal" badge in the
  sales timeline; the feed `url` is never serialized.
- Properties without iCal but with a `calendar_url` show a quick link that opens
  the owner's online calendar.
- A property with both shows the iCal badge (link suppressed).
- Test the serializer flag + precedence; FE renders badge vs link accordingly.

## Dependencies

- **Builds on:** GAP-011 (`PropertyCalendarFeed` already shipped) — this is part
  of its residual UI surfacing.
- **Related:** GAP-033 (iCal villas may derive freshness from `last_polled_at`).
