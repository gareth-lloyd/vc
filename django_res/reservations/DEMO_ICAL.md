# Demoing the iCal calendar-link import

The iCal feature is **import-only**: `ICalIngestService` polls each active
`PropertyCalendarFeed.url` over real HTTP, coalesces the busy ranges across a
property's feeds, and writes `OwnerBlock(source=ICAL)` rows that block
availability. There is no outbound/published feed and no owner-portal feed UI
(feeds are managed in Django admin).

The `demo_ical` management command stands up a self-contained demo property +
owner and drives the whole lifecycle. It is **additive, idempotent, and guarded
by `SEED_DEV_ALLOWED`** (refuses to run in production).

```
manage.py demo_ical --reset
manage.py demo_ical --setup [--owner-email … --owner-password …]
manage.py demo_ical --add-feed --platform <p> --label <l> --feed-url <ics>
manage.py demo_ical --poll                     # default action
manage.py demo_ical --inject-conflict quotation|booking
```

Run everything from `django_res/` with `DJANGO_SETTINGS_MODULE=villacollective.settings.dev`
and Postgres up (`docker compose up -d` from the repo root).

## Feed strategy

- **Real feed (headline):** a Google Calendar you control proves the genuine
  `httpx` fetch + RFC-5545 parse path. In Google Calendar → *Settings → Settings
  for my calendars → <calendar> → Integrate calendar → **Secret address in iCal
  format*** — copy that `…/basic.ics` URL.
- **Local fixtures (deterministic):** the cancellation / coalesce / conflict
  steps need the feed *contents* to change on demand, which a published OTA feed
  can't do promptly (Google/Airbnb refresh on a slow, uncontrollable cadence).
  Serve the editable fixtures in `management/commands/demo_fixtures/`:

  ```
  cd reservations/management/commands/demo_fixtures && python -m http.server 8765
  ```

  Then use `--feed-url http://localhost:8765/feed_a.ics`.

## Walkthrough

### 1. Import (real feed)

```
manage.py demo_ical --reset
manage.py demo_ical --setup
manage.py demo_ical --add-feed --platform google --label "Owner Google cal" \
    --feed-url "https://calendar.google.com/calendar/ical/<secret>/basic.ics"
manage.py demo_ical --poll
```

`--poll` prints each feed's fetch status, the `created/cancelled/conflicts`
counts, the imported blocks, and an availability calendar. Each imported block
is summarised inclusively — e.g. `2026-07-21 - 2026-07-30  (10 nights, free
from 2026-07-31)` — so the exclusive half-open `date_to` is never shown as a
blocked night. In the calendar, blocked days are `BLOCKED (owner_block)` and the
checkout day (the half-open end date) reads `OPEN — checkout / available`
rather than a bare `OPEN`.

### 2. Idempotent re-poll

```
manage.py demo_ical --poll      # → created=0 cancelled=0 (no-op)
```

### 3. Owner calendar API (BasicAuth)

The owner calendar endpoint authenticates with the owner's email + password
(the User model's `USERNAME_FIELD` is `email`):

```
curl -u demo.owner@example.com:demopass123 \
  "http://localhost:8000/api/v1/owner/properties/<id>/calendar?from=2026-07-10&to=2026-07-15"
```

Blocked days come back as `{"available": false, "reason": "owner_block"}`.
Unauthenticated requests are `403`.

### 4. Cancellation (local fixture)

Point the feed at the local server, poll, then remove the `VEVENT` from
`feed_a.ics` (leaving an empty `VCALENDAR`) and poll again:

```
manage.py demo_ical --add-feed --label Airbnb --feed-url http://localhost:8765/feed_a.ics
manage.py demo_ical --poll          # created=1
# …edit feed_a.ics: delete the BEGIN:VEVENT…END:VEVENT block…
manage.py demo_ical --poll          # cancelled=1, the dates free up
```

### 5. Multi-feed coalesce (local fixtures)

`feed_a.ics` (Jul 10–15) and `feed_b.ics` (Jul 14–18) overlap. Add both and the
poller merges them into **one** block (Jul 10–18):

```
manage.py demo_ical --add-feed --platform airbnb --label Airbnb --feed-url http://localhost:8765/feed_a.ics
manage.py demo_ical --add-feed --platform vrbo   --label Vrbo   --feed-url http://localhost:8765/feed_b.ics
manage.py demo_ical --poll          # one block [2026-07-10 … 2026-07-18)
```

### 6. Conflict + ops alert

A date VC has already sold (a confirmed booking) or quoted (an open quotation
hold) on the owner's other channel must **not** be overwritten — it alerts ops
instead. `--inject-conflict` cancels an imported block and plants the clash on
its range; the next poll re-imports, collides, and fires `ical_conflict_detected`:

```
export OPS_EMAIL_RECIPIENTS=ops@villacollective.test    # else the alert is silently skipped
manage.py demo_ical --inject-conflict quotation         # or: booking
manage.py demo_ical --poll                              # conflicts=1, created=0
```

**Observing the email in dev:** the alert is sent through `comms.EmailService`,
which requires an **active SYSTEM `SmtpProfile`** and writes an `EmailLog` row
(dev uses the locmem mail backend). With no SmtpProfile the send is skipped with
a `comms.email_skipped` log line — `conflicts=1` still proves the conflict path.
Inspect the email via the Django shell:

```
EmailLog.objects.filter(template_key="ical.conflict").values("to", "subject")
```

### 7. Reset

```
manage.py demo_ical --reset     # hard-deletes all demo rows (no soft delete)
```

`--reset` wipes everything tied to the demo property — including every row
that `PROTECT`s it: a booking's payments / refunds / security deposits /
booking events, the property's rate plans, *any* quotation with a line on it
(not just the demo guest's), and the enquiry events on the orphaned enquiries
that leaves behind. Nothing on this property is precious, so the reset clears
those first and then deletes the property; running it on a property carrying
real data would destroy real data.
