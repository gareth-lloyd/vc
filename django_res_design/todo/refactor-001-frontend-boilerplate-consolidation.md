# REFACTOR-001 — Consolidate repeated frontend boilerplate: CRUD-dialog state, FormDialog reset-effect, toast/error extraction, optimistic updates

- **Severity:** Refactor (frontend) — no behaviour change; collapse
  copy-pasted patterns into shared hooks/helpers before the copy count grows
  further.
- **Source:** the 2026-07-02 frontend complexity audit (god-components +
  cross-cutting). First member of the `refactor-*` bucket (see README).
- **Files (representative, not exhaustive):**
  - Dialog-state triple: `properties/tabs/PeopleTab.tsx:73–75,194–196,319–321,491–496`
    (13 `useState`), `rate-workbench/components/InspectorPanel.tsx:177–179,266–268,368–370`
    (10 `useState`).
  - `form.reset()`-in-`useEffect`: ~43 files call `form.reset`; ~28 FormDialogs
    (~6,800 LOC) repeat the skeleton, e.g. `SettingsTab.tsx:149,382,684`,
    `EnquiryFormDialog.tsx:148,158`. Most `react-hooks/exhaustive-deps`
    disables in the codebase suppress these effects + the
    `[params.toString()]` ListPage pattern (~7 pages).
  - Toasts: `toast` imported straight from `sonner` in **92 files / 264 call
    sites**, no wrapper; error extraction ad-hoc (~130 hand-rolled `.detail`
    accesses, 25 `.message`, only 18 `instanceof ApiError`, 2
    `apiErrorMessage`). `lib/api/errors.ts` defines `ApiError` but exposes no
    message-extraction helper.
  - Optimistic updates: three divergent copies —
    `bookings/hooks.ts:607` (`useToggleBookingNotePin`),
    `contacts/hooks.ts:132` (`useSetContactTags`),
    `rate-workbench/hooks.ts:87` (`useOptimisticBandPrice`, the only one with an
    `isMutating` settle-guard). `frontend/CLAUDE.md` still claims there is "one
    example."
  - God-components carrying the tax: `quotations/components/QuoteBuilder.tsx`
    (11 `useState` — search + pagination + staging + save-flow),
    `quotations/components/QuoteResultLine.tsx` (561 LOC, one component).

## Problem

The large frontend files are large mostly because the same four patterns are
re-typed per feature rather than shared. None is broken; together they are a
compounding maintenance tax and a bug surface (every hand-rolled optimistic
rollback / reset effect / error parse is a place to get it subtly wrong, and one
already differs — only the rate-workbench optimistic update has the
double-settle guard).

## Proposed fix

Extract a handful of shared primitives and migrate opportunistically (no
big-bang):

1. **`useCrudDialog()`** — the `addOpen / editing / deletingId` triple as one
   hook. Erases ~18 `useState` across PeopleTab + InspectorPanel alone and any
   future list-with-dialogs.
2. **A `FormDialog` / `useResourceForm` wrapper** owning the
   reset-from-props effect, the `topLevelError` + try/catch onSubmit block, and
   the exhaustive-deps suppression in one audited place — the ~28 dialogs stop
   re-implementing it and the lint-disable count drops sharply.
3. **`toastError(err)` + an `apiErrorMessage(err)` helper in `lib/api`** — one
   place that knows the `ApiError.detail` / `.message` / field-error shapes;
   replace the 264 raw `sonner` calls' error paths and the ~130 ad-hoc `.detail`
   reads.
4. **One `useOptimisticListUpdate` / `useOptimisticField` helper** — collapse
   the three snapshot/rollback copies onto the guarded implementation; update
   `frontend/CLAUDE.md` to point at it as *the* example.
5. **Decompose the two god-components** as they're touched: `QuoteBuilder`'s
   loading/results/pagination/save state is one machine → `useReducer`;
   `QuoteResultLine` splits into sub-components.

Items 1–4 are the high-leverage, mechanical wins; item 5 is opportunistic.

## Acceptance

- `useCrudDialog`, the FormDialog/`useResourceForm` wrapper, `toastError` /
  `apiErrorMessage`, and one optimistic-update helper exist in shared locations
  with tests.
- At least the cited PeopleTab / InspectorPanel dialog state and the three
  optimistic-update copies are migrated; `frontend/CLAUDE.md` references the
  single optimistic-update example.
- Net reduction in `react-hooks/exhaustive-deps` disables and in raw `sonner`
  error-path calls (grep before/after in the PR description).
- Quality gate green; zero behaviour change (existing vitest suites pass
  unmodified except where a component's internals are intentionally split).

## Dependencies

- Complements [BUG-018](bug-018-frontend-cache-staleness-missing-invalidations.md):
  BUG-018 owns the *cache-invalidation* consolidation (the entity→dependents
  map); this ticket owns the *optimistic-update* consolidation. Coordinate so
  the shared mutation helpers land once.
- No backend change.
