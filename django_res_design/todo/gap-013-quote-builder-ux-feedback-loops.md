# GAP-013 — Quote builder UX: tighten feedback loops

- **Severity:** 🟢 Gap (frontend UX polish) — no schema/service change. Operator-facing only.
- **Source:** 2026-06-09 frontend UX review of the inline quote builder. Sibling of
  [GAP-005](gap-005-quotation-flow-parity.md) (enquiry→quotation flow tracker).
- **Scope note:** Per-quote subtotal was **deliberately dropped** (`e29dd93`) — do
  **not** re-add a grand total. Customer-facing copy stays aligned with legacy
  `ResSystem`; tweaks below are operator-facing.
- **Files (all `frontend/src/features/quotations/components/`):**
  - `QuoteBuilder.tsx` — `handleRemove` (the currency `Select` /
    `handleCurrencyChange` references are gone — removed by GAP-014)
  - `QuoteShortlist.tsx` (was `QuoteCart.tsx`) — `ShortlistActions` disable-reason
    tooltip, `expandedId` ownership
  - `QuoteShortlistLine.tsx` (was `QuoteCartLine.tsx`) — collapsed header, money
    inputs (discount, total), `ChangeoverShiftedNote` render
  - `QuoteResultsList.tsx` — available row (L61–93), results `aria-live`
  - `ChangeoverShiftedNote.tsx`
  - `SaveQuoteDialog.tsx` — send-intent button copy, expiry hint

## Problem

The builder is architecturally sound (single canonical line-validity predicate
`stagedLineErrors`/`isStagedLineValid`, conditional dialog mounting, clean
RHF/Zod/React-Query, thorough i18n + a11y labelling). The gaps are in **feedback
loops** — the operator often can't see *why* something is blocked or *what* just
changed:

1. **Invalid lines are hard to locate.** A bad manual line disables Save/Send
   with a generic tooltip, but the operator must expand each `QuoteShortlistLine`
   to find the offending one.
2. **Line removal is silent + instant** (`handleRemove`) — no confirm, no undo,
   though staged lines are pure client state (cheaply recoverable).
3. ~~**Currency change wipes a non-empty cart**~~ **Moot** —
   [GAP-014](gap-014-quote-currency-forced-selection.md) removed the currency
   selector (and the cart-wipe) entirely; each villa prices in its own rate
   card's currency.
4. **Unpriceable "available" results can be added blind** — an `available`
   option with `total == null` renders "—"; the operator only learns it needs a
   manual total once it's in the cart.
5. **Changeover-shift note is easy to miss** (12px muted) yet signals priced
   dates differ from requested (GAP-007 behaviour).
6. **Two-dialog Send flow** (`SaveQuoteDialog` → `SendPreviewDialog`) is
   unsignposted — the operator doesn't expect a second modal.
7. **Disable reasons live only in a hover `Tooltip`** — no keyboard/SR path.
8. **Results swap in with no `aria-live`** — SR users aren't told the count.
9. **Polish:** money inputs are plain text with terse validation and no
   currency adornment; expiry default (today+7d, 23:59 UTC) is unexplained and
   UTC-only. (The currency-`Select` first-paint blank is moot — GAP-014
   removed the selector.)

## Proposed fix

Independent, individually shippable. Recommended order:

**High value / low effort**
- **(1)** Show a danger dot / `StatusBadge` (status tone from `globals.css`) on
  the collapsed line header when `stagedLineErrors(line)` is non-empty; surface a
  count ("1 line needs attention") and auto-expand the first invalid line when a
  disabled action is clicked. Lift `expandedId` control as needed.
- **(2)** Replace silent remove with a `sonner` toast carrying an **Undo** action
  that re-inserts the staged line (lighter than a confirm for recoverable state).
- **(3)** ~~Gate `handleCurrencyChange` behind a confirm~~ **Moot** — GAP-014
  deleted `handleCurrencyChange` and the selector.
- **(4)** In `QuoteResultsList`, render a "price unavailable — manual total
  required" note on available rows with `total == null`.

**Medium**
- **(5)** Promote `ChangeoverShiftedNote` to an info-tone (`--status-info`)
  chip/icon.
- **(6)** Relabel the send-intent primary button "Save & continue to preview".
- **(7)** Add a rendered + `aria-describedby` helper line under `CartActions`
  when blocked (don't rely on tooltip alone).
- **(8)** Wrap the results section in a polite `aria-live` region.

**Polish**
- **(9)** Currency-code adornment + "Amount in {currency}" hint on money
  inputs (per-line currency since GAP-014); one-line expiry hint clarifying
  the default + local time.

## Acceptance

- Invalid staged line is flagged on its collapsed header and clears when fixed;
  clicking a disabled action expands the first invalid line. (component test)
- Removing a line shows an Undo toast that restores it. (component test)
- ~~Changing currency with a non-empty cart prompts a confirm.~~ Moot (GAP-014).
- An available result with `total == null` shows the unpriceable note. (test)
- Results section announces count changes via `aria-live`; blocked actions expose
  their reason without hover.
- Quality gate green: `npm run lint && npx prettier --check . && npx tsc -b --noEmit && npx vitest run`.

## Dependencies

- Sibling of **GAP-005** (flow tracker) — coordinate if that overhaul reshapes
  the builder layout.
- **Coordinate with [GAP-043](gap-043-quote-builder-multi-week-range.md)
  (multi-week range) and [GAP-044](gap-044-occupancy-band-fanout-builder.md)
  (occupancy-band fan-out)** — both reshape the results/cart surface this ticket
  polishes (owner Loom 2026-06-17). Land the structural rework before (or with)
  these feedback-loop tweaks so the builder isn't reworked twice.
- **Q-013** (rate-card incomplete-pricing behaviour) — resolved: no-rate
  results now surface as flagged manual-quote cards in the main list, staged
  `is_manual` with required total + reason. The engine's null-total contract
  is unchanged; the unpriceable note for *available* options stays relevant.
- No backend dependency; all changes are frontend.
