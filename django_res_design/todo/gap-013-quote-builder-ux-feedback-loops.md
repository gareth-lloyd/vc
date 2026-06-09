# GAP-013 — Quote builder UX: tighten feedback loops

- **Severity:** 🟢 Gap (frontend UX polish) — no schema/service change. Operator-facing only.
- **Source:** 2026-06-09 frontend UX review of the inline quote builder. Sibling of
  [GAP-005](gap-005-quotation-flow-parity.md) (enquiry→quotation flow tracker).
- **Scope note:** Per-quote subtotal was **deliberately dropped** (`e29dd93`) — do
  **not** re-add a grand total. Customer-facing copy stays aligned with legacy
  `ResSystem`; tweaks below are operator-facing.
- **Files (all `frontend/src/features/quotations/components/`):**
  - `QuoteBuilder.tsx` — `handleRemove` (L157), `handleCurrencyChange` (L112),
    currency `Select` (L182–197)
  - `QuoteCart.tsx` — `CartActions` disable-reason tooltip (L92–113), `expandedId`
    ownership (L30)
  - `QuoteCartLine.tsx` — collapsed header (L52–73), money inputs (discount
    L94–115, total L141–156), `ChangeoverShiftedNote` render (L69)
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
   with a generic tooltip, but the operator must expand each `QuoteCartLine` to
   find the offending one.
2. **Line removal is silent + instant** (`handleRemove`) — no confirm, no undo,
   though staged lines are pure client state (cheaply recoverable).
3. **Currency change wipes a non-empty cart** with only a static hint; an
   accidental tap discards staged work.
4. **Unpriceable "available" results can be added blind** — an `available`
   option with `total == null` renders "—"; the operator only learns it needs a
   manual total once it's in the cart.
5. **Changeover-shift note is easy to miss** (12px muted) yet signals priced
   dates differ from requested (GAP-007 behaviour).
6. **Two-dialog Send flow** (`SaveQuoteDialog` → `SendPreviewDialog`) is
   unsignposted — the operator doesn't expect a second modal.
7. **Disable reasons live only in a hover `Tooltip`** — no keyboard/SR path.
8. **Results swap in with no `aria-live`** — SR users aren't told the count.
9. **Polish:** currency `Select` shows blank on first paint while currencies
   load (search disabled, unexplained); money inputs are plain text with terse
   validation and no currency adornment; expiry default (today+7d, 23:59 UTC) is
   unexplained and UTC-only.

## Proposed fix

Independent, individually shippable. Recommended order:

**High value / low effort**
- **(1)** Show a danger dot / `StatusBadge` (status tone from `globals.css`) on
  the collapsed line header when `stagedLineErrors(line)` is non-empty; surface a
  count ("1 line needs attention") and auto-expand the first invalid line when a
  disabled action is clicked. Lift `expandedId` control as needed.
- **(2)** Replace silent remove with a `sonner` toast carrying an **Undo** action
  that re-inserts the staged line (lighter than a confirm for recoverable state).
- **(3)** Gate `handleCurrencyChange` behind `components/feedback/ConfirmDialog`
  when `staged.length > 0`.
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
- **(9)** "Loading currencies…" placeholder in `SelectValue` while
  `currenciesQuery.isLoading`; currency-code adornment + "Amount in {currency}"
  hint on money inputs; one-line expiry hint clarifying the default + local time.

## Acceptance

- Invalid staged line is flagged on its collapsed header and clears when fixed;
  clicking a disabled action expands the first invalid line. (component test)
- Removing a line shows an Undo toast that restores it. (component test)
- Changing currency with a non-empty cart prompts a confirm; cancel keeps cart +
  currency. (component test)
- An available result with `total == null` shows the unpriceable note. (test)
- Results section announces count changes via `aria-live`; blocked actions expose
  their reason without hover.
- Quality gate green: `npm run lint && npx prettier --check . && npx tsc -b --noEmit && npx vitest run`.

## Dependencies

- Sibling of **GAP-005** (flow tracker) — coordinate if that overhaul reshapes
  the builder layout.
- **Q-013** (rate-card incomplete-pricing behaviour) informs item (4): if the
  engine's null-total contract changes, the unpriceable note should follow it.
- No backend dependency; all changes are frontend.
