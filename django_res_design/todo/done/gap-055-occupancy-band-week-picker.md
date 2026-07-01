> **✅ RESOLVED (2026-07-01)** — The GAP-044b two-axis picker. GAP-044 fanned
> out occupancy bands but **suppressed the week picker** for a banded villa and
> priced the bands for the **default changeover block only** — so an
> occupancy-priced villa showed "many prices, one week" while a flat villa
> showed "one price, many weeks", and the two axes never combined. That
> limitation is lifted: a banded villa now shows the **week picker *and* the
> selected week's bands** on one result card. Pick a week → its occupancy bands
> fan out as checkable, default-checked alternatives → each checked band saves
> as its own quotation line **at the chosen week's dates**.
>
> **Almost entirely frontend, zero new pricing cost.** The per-week reprice
> (`repriceStayOption`) already hits the same `POST /quotations:search-options`
> endpoint with `flex_days:0`, and `StayOptionsService._search_one` already
> attaches `occupancy_bands` for the priced block on **every** return path
> (including an out-of-bracket `party_out_of_range` reprice, which returns
> `available:false` **with** the full band array). So a per-week reprice already
> computes that week's bands — the frontend simply stopped discarding them. The
> only backend/wire change was adding `occupancy_bands` to `stayRepriceSchema`
> (Zod was silently stripping it). Search still eagerly prices only the
> **default** week's bands; an alternate week costs **one lazy reprice** — the
> existing flat-rate round-trip — so there is no new eager search cost and no new
> N+1 across the results list.
>
> **Key correctness properties.** The selected week's bands (`resolvedBands`) are
> read **decoupled from the reprice's `available` flag** — an out-of-bracket
> party still shows its bands and stays saveable (Add enabled). Checked bands are
> tracked by **party-range identity** (`${min_party}-${max_party}`) via a
> deselected-set, so a deselection survives a week flip and a newly-seen bracket
> defaults checked. `handleAdd` filters `resolvedBands` (the selected week) by
> identity, not the default option's array by index. Staging/save needed no
> change — `QuoteBuilder.useStayDates` already records a non-default week's dates
> and `SaveQuoteDialog.toLineWriteBodies` already expands each checked non-POA
> band at the staged line's dates. Bands remain **alternatives** (never summed)
> and the engine's single-band `quote()` contract is unchanged.
>
> **One acceptable performance caveat (H1):** un-suppressing the picker means a
> banded villa whose *default* block is booked now preselects its first-free
> alternate and reprices it **on mount** — identical to how flat-rate villas
> already behave, not a new class of load.
>
> Shipped frontend `d68c1c1` (F1 schema/wire) + `37f6936` (F2 `QuoteResultLine`
> two-axis rewrite, 3-angle high-effort review) + `479b7e3` (F3 end-to-end
> banded-on-alternate-week test). Deferred (unchanged from GAP-044): a per-week
> "from" price on the week chips (would need eager all-weeks pricing), changing
> the week from inside the shortlist (fixed at Add — change = remove + re-add),
> per-band manual override / discount, projection-year bands. Cross-refs:
> `04-pricing.md` (occupancy-band fan-out blockquote), `10-decisions.md`
> (occupancy-band fan-out row), `todo/done/gap-044-occupancy-band-fanout-builder.md`.

# GAP-055 — Quote builder: two-dimensional picker (week choice × occupancy bands) [GAP-044b]

- **Severity:** Gap (frontend; one-line backend wire) — lifts a GAP-044
  self-imposed limitation
- **Source:** Follow-up to GAP-044 (owner Loom 2026-06-17). Observed live on
  `/enquiries/498`: Casa Amber Hollow (occupancy-priced) offered no week choice
  while Casa Azure Crest (flat-rate) offered four weeks.
- **Area:** `frontend/src/features/quotations/` — `QuoteResultLine`, `schemas`,
  `api` (+ `QuoteBuilder`/`SaveQuoteDialog` verified, unchanged).

## Problem

GAP-044 decision 9 ("H3") deliberately suppressed the stay-option week picker
for an occupancy-priced villa and priced all bands for the default block only,
explicitly deferring the "bands × alternate changeover blocks" matrix. This left
the two pricing axes — **which week** and **which occupancy band** — unable to
combine on one card.

## What shipped

- **F1 — schema/wire (`d68c1c1`).** Add `occupancy_bands` to `stayRepriceSchema`
  so a per-week reprice surfaces that week's bands (the backend already sent
  them; Zod was stripping the field). No new backend test warranted — existing
  `test_stay_options` tests already pin party-independent bands + the 28-query
  budget for `flex_days:0`.
- **F2 — `QuoteResultLine` two-axis rewrite (`37f6936`).** Show the week picker
  for banded villas; resolve the selected week's bands (`resolvedBands`,
  decoupled from `available`); track checked bands by party-range identity;
  gate Add on `staged || heldSelected || (banded ? no saveable checked band :
  price unresolved)`; `handleAdd` filters `resolvedBands` by identity and carries
  the picked week's dates; the shifted-date warning and "Repricing…" placeholder
  now apply in banded view. Rewrote the two now-contradicting tests and added a
  two-axis suite (flip-reprices-bands, deselection persists across flips,
  out-of-bracket week saveable, flat alternate renders a total, repricing
  placeholder, changeover-shift warning, held week disables Add, picked
  week's dates+bands reach onAdd, POA-passthrough contract).
- **F3 — end-to-end test (`479b7e3`).** A `QuoteBuilder` test proving a banded
  villa added on an *alternate* week stages and saves at that week's dates with
  that week's band prices (one non-manual line per band).

## Deferred (do not re-raise)

- Per-week "from" price on the week chips (needs eager all-weeks pricing).
- Changing the week from inside the shortlist (chosen: fixed at Add).
- Per-band manual override / per-band discount (line-level only, as GAP-044).
- Projection-year bands.
