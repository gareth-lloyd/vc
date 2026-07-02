# GAP-013 — Quote builder UX: tighten feedback loops

- **Severity:** 🟢 Gap (frontend UX polish) — no schema/service change. Operator-facing only.
- **Source:** 2026-06-09 frontend UX review of the inline quote builder. Sibling of
  [GAP-005](gap-005-quotation-flow-parity.md) (enquiry→quotation flow tracker).
- **Audited 2026-07-02** against the post-[GAP-043](done/gap-043-quote-builder-multi-week-range.md)
  /[GAP-044](done/gap-044-occupancy-band-fanout-builder.md) builder (multi-week strip,
  occupancy-band fan-out, rebuilt result cards). Still substantially relevant: 6 of the
  original 9 items open, 2 partially fixed, the rest moot. Statuses and file targets
  below reflect that audit.
- **Scope note:** Per-quote subtotal was **deliberately dropped** (`e29dd93`) — do
  **not** re-add a grand total. Customer-facing copy stays aligned with legacy
  `ResSystem`; tweaks below are operator-facing.
- **Files (all `frontend/src/features/quotations/components/` unless noted):**
  - `QuoteBuilder.tsx` — `handleRemove` (L213–215), results `<section>` (L245–273)
  - `QuoteShortlist.tsx` — `anyInvalid`/`disableReason` gate (L49–58), tooltip-wrapped
    actions (L106–127), fresh-manual-line auto-expand (L35–47)
  - `QuoteShortlistLine.tsx` — header error region (L127–131), expanded-only
    discount/reason errors (L170, 234, 250), Remove button (L148–150), money inputs
    (discount L161–180, manual total L222–232), `ChangeoverShiftedNote` render (L132–135)
  - `QuoteResultLine.tsx` — **new since the original ticket**; owns the results-surface
    items: per-week price cell (L522–531), `weekAddable` (L260–270), warning-tone
    changeover lines (L535–544), band checkboxes
  - `QuoteResultsList.tsx` — priced-count line (L280–286), manual-quotable card split
    (L159–226)
  - `SaveQuoteDialog.tsx` — confirm button copy (L261–263), `defaultExpiresAt` (L35–42),
    expiry hint (L247)
  - `StayOptionPicker.tsx` — the GAP-043 week strip (context only; no changes expected)

## Problem

The builder is architecturally sound (single canonical line-validity predicate
`stagedLineErrors`/`isStagedLineValid` in `lineTotals.ts`, conditional dialog mounting,
clean RHF/Zod/React-Query, thorough i18n + a11y labelling). The gaps are in **feedback
loops** — the operator often can't see *why* something is blocked or *what* just
changed:

1. **Invalid lines are hard to locate** *(partially fixed)*. Total-price and
   `bands_none_checked` errors now render in the always-visible line header
   (`QuoteShortlistLine.tsx:127-131`, `role="alert"`), but discount/reason errors are
   only visible once the line is expanded, and there is no danger dot / badge, no
   "N lines need attention" count, and no auto-expand of the first invalid line when a
   disabled action is clicked (the only auto-expand is for freshly staged no-rate
   manual lines).
2. **Line removal is silent + instant** (`handleRemove`) — no confirm, no undo,
   though staged lines are pure client state (cheaply recoverable). (The
   "Remove this line?" ConfirmDialog in `en/quotations.json` belongs to the
   persisted-quote `LineEditDialog` path, not the builder shortlist.)
3. **Unpriceable "available" weeks can be added blind** *(narrowed by Q-013)*. No-rate
   villas are now carved into flagged manual-quote cards, but an `available` week with
   `total == null` still renders a bare "—" in the result card, and `weekAddable`
   happily stages it — the operator only learns it needs a manual total once it flags
   invalid in the shortlist.
4. **Two-dialog Send flow** (`SaveQuoteDialog` → `SendPreviewDialog`) is
   unsignposted — `saveIntent` is never passed into the dialog, so the primary button
   reads "Save quote" for both draft and send flows.
5. **Disable reasons live only in a hover `Tooltip`** — no keyboard/SR path
   (zero `aria-describedby` in the feature).
6. **Results swap in with no `aria-live`** — SR users aren't told the count; the
   priced-count line is a plain `<p>`.
7. **Polish:** the manual-total input gained a trailing currency adornment, but the
   discount input is still a plain unadorned text input; the expiry hint explains
   what expiry *means* but not the default (today+7d, local end-of-day). The
   shortlist-side `ChangeoverShiftedNote` is still 12px muted text (result cards now
   surface shifts in warning tone, so this is downgraded to optional).

Resolved since the original review: the currency selector and its cart-wipe were
removed entirely by [GAP-014](done/gap-014-quote-currency-forced-selection.md) (each
villa prices in its own rate plan's currency) — the confirm-on-currency-change and
selector-first-paint items are **moot**.

## Proposed fix

Independent, individually shippable. Recommended order:

**High value / low effort**
- **(1)** Show a danger dot / `StatusBadge` (status tone from `globals.css`) on the
  collapsed line header when `stagedLineErrors(line)` is non-empty (build on the
  existing header `role="alert"` region — extend it to cover discount/reason errors);
  surface a count ("1 line needs attention") near the actions and auto-expand the
  first invalid line when a disabled action is clicked. Lift `expandedId` control as
  needed (it already lives in `QuoteShortlist.tsx`).
- **(2)** Replace silent remove with a `sonner` toast carrying an **Undo** action
  that re-inserts the staged line (lighter than a confirm for recoverable state).
- **(3)** In `QuoteResultLine.tsx`, render a "price unavailable — manual total
  required" note on available weeks with `total == null` (instead of the bare "—"),
  so the operator knows before staging.

**Medium**
- **(4)** Pass `saveIntent` into `SaveQuoteDialog` and relabel the send-intent
  primary button "Save & continue to preview".
- **(5)** Add a rendered + `aria-describedby` helper line under the shortlist
  actions when blocked (don't rely on tooltip alone).
- **(6)** Wrap the results section in a polite `aria-live` region so count changes
  are announced.

**Polish**
- **(7)** Currency-code adornment on the discount input (matching the manual-total
  input's trailing-span pattern in `QuoteShortlistLine.tsx:222-232`) + extend the
  expiry hint to state the default (today+7d, local end-of-day).
- **(8)** *(optional, downgraded)* Promote the shortlist-side `ChangeoverShiftedNote`
  to an info-tone (`--status-info`) chip/icon; result cards already show shifts in
  warning tone.

## Acceptance

- An invalid staged line is flagged on its collapsed header (including
  discount/reason errors) and clears when fixed; a "N lines need attention" count
  shows near the actions; clicking a disabled action expands the first invalid line.
  (component test)
- Removing a shortlist line shows an Undo toast that restores it. (component test)
- An available week with `total == null` shows the unpriceable note in the result
  card. (component test)
- The send-intent flow's primary button signposts the preview step; the draft flow's
  copy is unchanged. (component test)
- Results section announces count changes via `aria-live`; blocked actions expose
  their reason without hover (`aria-describedby` + rendered text).
- Quality gate green: `npm run lint && npx prettier --check . && npx tsc -b --noEmit && npx vitest run`.

## Dependencies

- Sibling of **GAP-005** (flow tracker) — coordinate if that overhaul reshapes
  the builder layout.
- ~~Coordinate with GAP-043 / GAP-044~~ **Done** — both landed
  ([GAP-043](done/gap-043-quote-builder-multi-week-range.md),
  [GAP-044](done/gap-044-occupancy-band-fanout-builder.md)); this ticket's targets
  now reflect the reworked surface (`QuoteResultLine.tsx`, week strip, band
  checkboxes).
- **Q-013** (rate-card incomplete-pricing behaviour) — resolved: no-rate results
  surface as flagged manual-quote cards, staged `is_manual` with required total +
  reason. The engine's null-total contract is unchanged; the unpriceable note for
  *available* weeks (item 3) is the surviving case.
- No backend dependency; all changes are frontend.
