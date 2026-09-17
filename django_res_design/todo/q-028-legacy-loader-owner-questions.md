# Q-028 — Open questions for Nick: legacy-loader residue, season labels, ambiguous room floors, and discounts on reprice

> **Scope widened 2026-09-16 (todo consolidation):** this is now the single
> list of questions waiting on Nick. It absorbs **Q-022** (season labels →
> question 6) and **Q-025** (ambiguous floor rungs → question 7), and carries
> the product decision **BUG-025** needs (question 8 — BUG-025's code shipped
> 2026-09-17 provisionally on the suggested answer; the question stays open). The absorbed tickets' full text is kept as "Merged from"
> sections at the end. Questions that belong to a specific call stay with
> that call: odd-length stay pricing (D1–D3) is on **GAP-074**'s owner/Debbie
> agenda. Questions 1–5 below are the original loader residue.

- **Severity:** Question (each blocks one small slice of loader work; none
  blocks cutover on its own).
- **Source:** 2026-09-11 legacy-loader audit. Everything the audit *could*
  decide from the dump or the legacy code was decided the same day (recorded
  in BUG-028 / BUG-029 / BUG-030 / GAP-108 / GAP-109 and to be written into
  `design/decisions.md` as they land). The residue below needs the owner.
- **Files:** `django_res/data_migration/management/commands/import_past_bookers.py:206-256`;
  `django_res/data_migration/loaders/properties.py` (concierge tier);
  `django_res/data_migration/loaders/property_children.py:83-164`
  (`GallaryOrder`); `django_res/data_migration/loaders/pricing.py:534-543`
  (extras — GAP-107 §1).
- **Format:** numbered, each with a suggested answer so a one-word reply per
  number is complete, in the style of
  [owner-questions-2026-07-02.md](reviews/owner-questions-2026-07-02.md). Fold onto
  the next Nick call rather than sending as a standalone e-mail.

## Questions

1. **Future stays in the Past Bookers sheet.** The Booking History sheet has
   141 stays dated 2026 and 17 dated 2027 (plus 160 for 2025). Today they
   import as "past stays" and make those guests count as repeat customers
   before they have stayed. **Suggested answer:** skip anything dated after
   the cutover year and list them in the import report; they are bookings-to-
   be and will arrive through the normal booking flow. *(Alternative: keep
   them all — a stay is a relationship fact regardless of date.)*

2. **Concierge tier per villa.** Legacy stores a concierge service tier on
   291 live villas (tier 1 ×165, tier 2 ×126). The new system has no field
   for it and concierge is deferred to M2. **Suggested answer:** keep the
   number on the villa as a plain "concierge tier" field now (cheap, nothing
   reads it yet) rather than lose it and re-derive from the archived dump
   later. *(Alternative: drop it; we have the dump.)*

3. **Featured-image grid slots.** Legacy's image screen lets a curator pin
   up to four images into a "featured grid" (696 images carry a slot 1–4).
   The new gallery has a hero and a sort order, no slots. **Suggested
   answer:** ask Ben whether the rebuilt website (GAP-106) wants a featured
   grid; if yes we carry the slot across, if no we drop it and record the
   count. *(Depends on Q-026 / GAP-106.)*

4. ~~**Legacy extras catalogue**~~ — **answered, drop from the call.**
   User decision 2026-09-10, shipped in GAP-107 (merged 2026-09-14): the 96
   live legacy extras (not 137) port as **opt-in** `pricing.Extra` rows with
   **no date window** (legacy `FromDate`/`ToDate` on extras are 2022 fold-in
   timestamps and would hide every extra from quotes); 84 load. Quoting them
   from the builder waits on GAP-111.

5. **Do we ever run two price lists for one villa at once — a gross public
   one and a net agent one — on the same dates?** (GAP-110.) The 2026-06-22
   net/gross decision text says yes in principle; no legacy villa does it
   (all 521 loaded plans are gross) and the quote path has no way to pick
   one. GAP-110 forbids two plans pricing the same night in one currency.
   **Suggested answer:** no — one list per villa per currency; a switch
   from gross to net happens at a season boundary. *(If yes: the plan
   gains a segment, the invariant becomes per villa + currency + segment,
   and the quote path must let staff choose the segment. Small, but must
   be known before GAP-110 U2.)*
   **Recorded 2026-09-14 (GAP-110 shipped, U2 landed):** the partition is
   `(property, currency)` with **no `segment`** — `rateperiod_no_overlap` is
   per villa + currency, and at most one *active* plan exists per villa +
   currency + price basis. A GROSS and a NET plan can therefore coexist only
   on **different dates**; a stay touching both is a loud `MultiRegimeStay`
   error, never a silent pick. Agent-vs-direct pricing on the *same* dates
   would need a `segment` on the plan, the invariant widened to
   `(property, currency, segment)`, and a segment selector on the quote
   path — a small extension, but it is **still open for the owner**: the
   question stands as asked.

6. **Season labels — confirm the fixed list** (was Q-022 / C1 of the
   2026-07-02 round). You label bunches of weeks as a season for reporting
   ("peak-season bookings up X%") and pricing decisions; each villa keeps
   its own dates and the labels are what line up across villas.
   **Suggested answer:** **Top peak / Peak / High / Shoulder / Low** — five
   labels, used by every villa, each villa deciding which of its weeks
   carry which label. Two checks: (a) any label missing or surplus? (b) for
   a villa that charges the same rate all year, is one tier (or unlabelled
   weeks) acceptable, or do you want a *Standard* label?

7. **Room floors the old system describes vaguely** (was Q-025). "Master -
   First floor" already comes across correctly, and anything not understood
   keeps its original wording in a note, so nothing is lost. The open part is
   the vague ones — "upper floor", "upper level", "lower level",
   "mezzanine", "basement" — which are left blank today. **Suggested
   answer:** leave them blank with the note kept; staff pick the floor when
   they next edit the room. Also: should room *names* ("Master 1") be read
   for position too? **Suggested answer:** no. *(Take the top unparsed
   strings by frequency to the call — Q-025 §"Proposed direction" step 1.)*

8. **A discount when a booking is repriced** (for BUG-025). If a booking
   with an agreed discount changes dates or party size, the system reprices
   it — and today the discount silently disappears. Should it (a) keep the
   same amount off ("we agreed £150 off"), (b) scale it with the new price,
   or (c) drop it and warn staff to re-enter it? **Suggested answer:** (a)
   keep the same amount off, never below zero.
   *(2026-09-17: BUG-025 shipped **provisionally** on (a) —
   `BookingService.reprice_snapshot`. Still ask: an answer of (b) or (c)
   reopens it as a change to that one helper.)*

## Disposition

Record each answer in `design/decisions.md` and on the owning ticket
(1 → BUG-030 §36; 2, 3 → GAP-109 rows 10/11; 4 → GAP-107 §1; 5 → GAP-110
U2; 6 → `season_tier` controlled enum at the rate-period level, copies with
the base on carry-over — §"Merged from Q-022"; 7 → pattern change or
blank-with-note, then A2 confirmed in `design/decisions.md` — §"Merged from
Q-025"; 8 → BUG-025); retire this file to `reviews/` when all are answered.

**2026-09-15:** BUG-030 closed with §36 deliberately untouched — the future
Past Bookers stays still land as `PastStay`. BUG-030 is in `done/`, so the
answer to question 1 needs its own small ticket against
`import_past_bookers`.

---

## Merged from Q-022 — Seasons defined by rental rates, not services

> _Folded in 2026-09-16 (todo consolidation). The standalone ticket is closed as
> [Q-022](done/q-022-seasons-defined-by-rates.md); the text below is that ticket as it stood, headings
> demoted one level. A reference to Q-022 elsewhere now means this section._

- **Severity:** Question (modelling decision; reporting impact)
- **Source:** 2026-06-11 email thread (Nick Cookson + Bryony Moger);
  2026-06-17 owner Loom (pricing walkthrough, 1:30–2:40)
- **Files:** `django_res_design/04-pricing.md` (rewritten as-built by Q-018;
  model now `Property → RatePlan → RatePeriod → RateBand` — see the
  2026-07-29 note below), `django_res_design/02-properties.md`,
  `django_res/pricing/models/rate.py` (`RatePeriod` — candidate tier home)

### Problem

Nick proposed that **seasons be defined by rental rates** rather than by
services (the legacy basis). His reasoning is twofold: it reads better for
**reporting** (e.g. "peak-season bookings up X%, mid down X%") and it maps
naturally to **pricing** decisions ("20% reduction from peak to high").

Bryony agreed seasons should be defined by the villa's rental rates, **but**
flagged that each villa has a **different seasonal structure** — some are
flat year-round, some treat peak as Jul/Aug, and some use bespoke ranges
like 8 Jul–22 Aug. Her concern: this per-villa variability complicates
**standardised reporting** across peak/shoulder/low, because there is no
single calendar-aligned definition of a "season" to aggregate on.

The same email also touched on **Villa Groups** being removed — but per the
rebuild that decision was **deferred** (groups stay; see q-021).

### Owner answer (2026-06-17 Loom)

The owner resolved Q2/Q3: a **season is a named tier/category** — he listed
*top peak season*, *peak / high season*, *shoulder season* — that an operator
**applies over week-priced rate bands** by "bunching certain dates or certain
weeks together" and labelling the group. The season is therefore **a category
attached to the bands, not the `RatePlan` itself** ("we want to be able to put
prices per week, and then be able to categorize certain sections of the pricing
calendar as high season / peak").

Its primary driver is **cross-villa reporting** ("peak-season bookings up X%,
mid down X%") and pricing decisions ("20% reduction peak→high") — which is why a
free-text label is insufficient: it must be a controlled tier that aggregates
across villas despite each villa's bespoke date ranges. Q1 (cross-villa
standardisation, Bryony's concern) remains the one open question.

### Open questions

1. How are season tiers (top-peak/peak/high/shoulder/low) **standardised for
   cross-villa reporting** when each villa defines its own date ranges?
   (Bryony's concern — still open.)
2. ~~Is "season" a named/categorised band, or just the rate bands themselves?~~
   **Answered:** a named tier/category applied over rate bands.
3. ~~Is the season the rate plan, the band, or a category attached to either?~~
   **Answered:** a category attached to the bands.

### Proposed fix / direction

> **2026-07-29 rewrite (model drift):** this section originally targeted the
> pre-GAP-056 `RatePlan`/`RateCard`/`RateRule` model — `RateCard` was dropped
> and `RateRule` renamed `RateBand`; the current model is
> `Property → RatePlan → RatePeriod → RateBand` (GAP-056 / SMELL-019). The
> mechanics below are restated against it; the owner answer is unchanged.

Introduce a controlled `season_tier` enum (curated set — confirm exact list
with product; owner named TOP_PEAK / PEAK·HIGH / SHOULDER, plus a LOW for
year-round flat villas). The natural home in the current model is
**`RatePeriod`** — a period is already exactly the owner's "bunch of weeks
with a label" (named, date-windowed, per-villa), so the tier is a second,
controlled label alongside `RatePeriod.name` (GAP-059) rather than a per-band
attribute; reporting aggregates on the tier while each villa keeps its own
dates. Note that the tier must **copy with the base** on carry-over (Q-018 —
carry-over already copies the base, not any in-season reduction), and that
[SPEC-001](done/spec-001-rateplan-date-authority-regime-bucket.md) explored making
`RatePeriod` the sole date authority — **built 2026-09-14 as GAP-110** (the
plan is a date-less regime bucket; carry-forward writes periods into it, so a
tier on the period would ride the same clone). A tier-on-period decision here
should be made with that shape in view (it strengthens the period's claim to
be the season-shaped object). Leave the cross-villa reporting standardisation
(open question 1) for the reporting design.

### Acceptance

- Decision recorded in `10-decisions.md`.
- Relevant pricing design doc updated (`04-pricing.md` / `02-properties.md`).
- Model implications scoped (`season_tier` placement on `RatePeriod` vs
  `RateBand`).

### Dependencies

- Relates to GAP-025 / Q-018 (rate entry; tier copies with the base on
  carry-over).
- GAP-037 (services split): the **inclusions** half of the legacy "season"
  moves to a Services concept; this ticket keeps the **rate-tier** half.
- The pricing model (`Property → RatePlan → RatePeriod → RateBand`, GAP-056);
  [SPEC-001](done/spec-001-rateplan-date-authority-regime-bucket.md) (period as
  date authority — structural counterpart to this question).

---

## Merged from Q-025 — Room floor: A2 ladder seen and endorsed; settle the unparsed remainder

> _Folded in 2026-09-16 (todo consolidation). The standalone ticket is closed as
> [Q-025](done/q-025-room-floor-ladder-confirmation-parse-gap.md); the text below is that ticket as it stood, headings
> demoted one level. A reference to Q-025 elsewhere now means this section._

- **Severity:** Question (owner confirmation + a known reconcile gap).
  **No new build** — GAP-065 already shipped everything Nick asked for.
- **Source:** 2026-07-20 Nick screen-recording (`Recording-20260720_134424`,
  reviewed 2026-08-11), relaying Brian E. Transcript `[04:45–05:10]`; our Add
  room dialog captured at `[04:55]`.
- **Files:**
  - `django_res/data_migration/placement_parsing.py` — `parse_placement`
    (GAP-065), keyword parser over legacy `VillaRoomsPlacement.Name`.
  - `django_res/properties/enums.py:70` — `RoomFloor` (the A2 ladder).
  - `django_res/data_migration/loaders/property_children.py:46–53` — raw
    string preserved verbatim in `Room.placement_note`.
  - `done/gap-065-room-location-building-floor.md` — the shipped build.

### What the recording settles

Brian's note, via Nick `[04:48]`: *"the floor is not a dropdown on our current
res system, it's actually free text… I think a dropdown would be much
better."*

**This already exists.** The Add-room dialog at `[04:55]` shows Floor as a
dropdown — *Not set / Lower ground floor / Ground floor / First floor /
Second floor / Third floor or above* — alongside a separate Placement axis.
That is GAP-065's `RoomFloor` ladder, shipped 2026-07-05 on the **ticket
default A2 vocabulary with owner confirmation pending**. Nick is looking
straight at it and endorsing it, so **treat A2 as confirmed** unless someone
objects — and record that in `design/decisions.md`, where it currently sits
under "Open follow-ups".

### What is still open

Nick `[04:57]`: *"I'm just slightly concerned about how that's going to pull
through from the previous system… I think how it's done is 'Master - First
floor'. So I'm not sure how that's going to pull over, but that's something
perhaps we can talk about."*

The mechanism exists — `parse_placement` word-matches
`\bfirst[\s-]+fl?oor` (the typo `"First foor"` is handled), so
`"Master - First floor"` does parse to `FIRST`, and anything unparsed keeps
its raw string in `placement_note`, so nothing is lost. Two residuals remain:

1. **The 49-row reconcile gap.** GAP-073's live dry-run on the 24-Apr dump
   surfaced a `Room placement (GAP-065)` reconcile gap of **49** rows, listed
   there as a pre-existing follow-up and never chased. That is the concrete
   answer to Nick's question and should be quantified before the
   conversation, not during it. Note the check itself
   (`reconcile_legacy.py:187–206`) still carries `expected_gap=0` marked
   **PLACEHOLDER — recalibrate at the first cutover dry-run**, and already
   names the two legitimate causes to apportion the 49 across: rooms whose
   parent property wasn't loaded (the 307 slice above it), and dangling
   `PlacementId` → blank `VillaRoomsPlacement.Name`. So the number is not
   evidence of a parser failure until that apportionment is done — and it may
   resolve to "recalibrate the constant", not "extend the patterns".
   **Apportioned 2026-09-11 (loader audit, scratch-DB dry-run):** 49 = **46**
   rooms on villas not loaded (deleted / blank-name villa 249) + **3** rooms
   with a dangling `PlacementId` (4 ids absent from `VillaRoomsPlacement`).
   Zero parser failures. GAP-108 pins the constant at 49; this residual is
   closed and only item 2 remains for the call.
2. **Ambiguous rungs stay blank by design** — `"upper floor"`, `"upper
   level"`, `"lower level"`, `"mezzanine"`, `"basement"` deliberately parse to
   `""` pending the A2 steer. With Nick on the call this is answerable: do
   these get ladder rungs, or stay unset with the note?

Worth noting the room he types in the video is named **"Master 1"** — legacy
room *names* also carry position information, a second channel the parser
doesn't read.

### Proposed direction

1. Run `parse_placement` over the current snapshot and produce a coverage
   count: parsed to a floor / parsed to a building / left blank, with the top
   unparsed strings by frequency. That's a half-hour query and it turns the
   worry into a number.
2. Take the top unparsed strings to Nick with the two questions above
   (ambiguous rungs; whether room *names* should be a parse source).
3. Extend the patterns or accept the remainder as blank-with-note, then close
   the GAP-073 reconcile row.
4. Record the A2 confirmation in `design/decisions.md`.

### Acceptance

- Parse coverage measured and recorded; the 49-row gap explained or closed.
- Ambiguous-rung decision recorded in `design/decisions.md`.
- A2 ladder marked confirmed (or revised) in `design/decisions.md`.

### Dependencies

- **GAP-065** (resolved) — the build being confirmed here.
- **GAP-073** (resolved) — surfaced the 49-row reconcile gap.
- Related: **GAP-064** A1 room-attribute vocabulary, the sibling pending
  owner confirmation — worth putting to Nick in the same conversation.
