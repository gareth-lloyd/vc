# GAP-083 — Features tab: flag unsaved changes + block navigation without explicit discard

- **Severity:** 🟢 Gap (UX / data-loss guard). Frontend-only.
- **Source:** Gareth GTD capture 2026-07-08 ("When editing property features,
  requires an explicit save. Should be flagged that data has changed, and no
  navigate without explicit reject changes"). Filed 2026-07-29 after checking
  the codebase.
- **Files touched (best-guess):**
  - `frontend/src/features/properties/tabs/FeaturesTab.tsx` — already computes
    an order-sensitive `isDirty` (~L153) and gates Save/Reset on it (~L275,
    ~L297); the button state is the *only* dirty signal.
  - `frontend/src/features/properties/PropertyDetailLayout.tsx` — tabs are
    route-based `NavLink`s over an `<Outlet>` (~L86-134); switching tab
    unmounts `FeaturesTab` and the dirty `order` state is silently discarded.
  - `frontend/src/app/router.tsx` — `createBrowserRouter` (React Router v7),
    so `useBlocker` is available for in-app navigation guarding.
  - `frontend/src/components/feedback/ConfirmDialog.tsx` — existing primitive
    for the discard confirmation.

## Problem

The features grid is explicit-save (deliberate — reordering is a real edit,
GAP-022), but nothing tells the operator they have unsaved changes beyond the
Save button un-greying, and nothing stops them losing work: clicking any other
tab, the sidebar, or the browser back button unmounts the tab and throws the
edits away with no warning. `grep useBlocker\|beforeunload frontend/src` — no
hits; the app has no navigation-guard pattern anywhere yet.

## Proposed fix

- **Visible dirty flag** — when `isDirty`, show an explicit "Unsaved changes"
  indicator (e.g. badge/banner next to the Save/Reset controls), not just an
  enabled button.
- **In-app navigation guard** — `useBlocker(isDirty)` (+ save-mutation-pending
  exemption) → `ConfirmDialog`: stay / discard-and-leave. Leaving requires an
  explicit discard; Save stays a deliberate separate action (no save-on-exit
  magic).
- **Hard-exit guard** — `beforeunload` handler while dirty for reload/close
  (browser-native prompt; best-effort only).
- Build it as a small reusable hook (e.g. `useUnsavedChangesGuard(isDirty)` in
  `src/lib/` or `components/feedback/`) — the same hazard exists on every
  explicit-save surface (SettingsTab sections, DescriptionsSection, …), but
  **scope this ticket to FeaturesTab as the pilot**; roll-out elsewhere is
  follow-up.

## Acceptance

- With unsaved feature edits, an "unsaved changes" indicator is visible.
  (component test)
- Navigating to another tab/route while dirty opens a confirm dialog; cancel
  stays put with edits intact, confirm leaves and discards. (component test)
- Saving clears the flag and navigation is unobstructed when clean or right
  after save. (test)
- Quality gate green (frontend).

## Dependencies

- None hard. Related: GAP-022 (explicit-save ordered features grid — the
  behaviour being guarded); roll-out to other explicit-save tabs is a
  candidate follow-up ticket.
