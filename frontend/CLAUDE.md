# Frontend — React SPA

Vite + React + TypeScript SPA. shadcn/ui component library, React Query
for server state, React Hook Form + Zod for forms, React Router v7 for
routing.

## Local setup

1. `cd frontend && npm install`
2. Backend must be running (`docker compose up -d` + Django dev server).
3. `npm run dev` — Vite dev server at `localhost:5173`.
4. `npm run lint && npx prettier --check . && npx tsc -b --noEmit && npx vitest run`
   — full quality gate.

## Conventions

Patterns already in the code. New work should mirror them.

### Feature module layout

Each feature lives in `src/features/<name>/` with a standard shape:

    schemas.ts       — Zod schemas for API responses AND write inputs
    api.ts           — fetch functions (apiGet/apiSend + Zod parse)
    hooks.ts         — React Query useQuery/useMutation wrappers
    columns.tsx      — DataTable column defs (if the feature has a list)
    <Page>.tsx       — page components
    <Layout>.tsx     — detail layout with tabs
    tabs/            — tab components rendered via Outlet
    components/      — dialogs, pickers, sub-components
    __tests__/       — colocated tests

A feature may contain a folded sub-feature directory keeping this same shape
when the sub-feature is one-way coupled to its owner — `properties/
rate-workbench/` is the only one (see Module boundaries); don't copy the
pattern without that justification.

### Module boundaries (GAP-063)

Features import only themselves, `src/lib/`, and `src/components/` — never
another feature. What lint enforces is the cross-feature ban specifically:
`eslint-plugin-boundaries` (`eslint.config.js`) errors on any
feature→feature import whose pair is not in `ALLOWED_EDGES`
(`boundaries.allowlist.js`), a **shrink-only ratchet** of pre-existing
coupling (the backend import-linter model, FG-013). Entries may be removed as
edges are paid down, never added — the one exception is a documented relabel
when shared code moves to its true home feature. A vitest guard
(`src/test/boundaries.test.ts`) fails if an entry goes stale, so paid-down
edges must be deleted. New cross-feature needs go to `src/lib/domain/`
(shared Zod schemas/labels) or `src/components/` (shared UI). Test files are
exempt (cross-feature MSW handlers and scaffolding are fine there).

rate-workbench is a `properties` sub-feature
(`features/properties/rate-workbench/`), not a standalone feature (GAP-063
decided fold over promotion: its 29 imports were one-way into properties).

### Zod-first types

Every API response type is `z.infer<typeof schema>`, never hand-typed.
Write-input schemas live in the same `schemas.ts` and power `zodResolver`.
The API layer parses every response through the schema before returning it.

### API client

`apiGet` for reads, `apiSend` for writes (`lib/api/client.ts`). Always call as
`apiGet<unknown>(path)` and parse with a Zod schema — never trust the raw
response type. Custom actions use colon-verb syntax:
`POST /bookings/{id}:confirm`.

### React Query

- **Query keys**: factory in `lib/query/keys.ts`; nest detail sub-resources
  under their parent (`["properties", "detail", id, "contacts"]`).
- **Conditional queries**: `enabledQuery(id, keyFor, fetchFor)` for any hook
  whose parameter might not be available yet.
- **Mutations**: invalidate the narrowest relevant key; no manual cache
  updates unless optimistic UI is needed (`useToggleNotePin` is the one
  example).
- **Auth boundaries wipe the whole cache.** Login, 2FA verify, logout, and the
  boot-level 401 handler all funnel through `resetAuthQueryCache`
  (`features/auth/resetAuthQueryCache.ts`) — never a hand-picked prefix
  allowlist, which leaks one user's cached data into the next session. Any new
  auth transition must call it too.

### Form dialog pattern (create / edit)

Discriminated union props: `{ mode: "create" }` | `{ mode: "edit"; entity: T }`.
Each dialog is self-contained — no shared form dialog abstraction. Template:
`NoteFormDialog.tsx`.

- Reset form state in a `useEffect` gated on `open`.
- **4xx field errors**: `applyApiErrorToForm(form, error)` maps
  `field_errors` to RHF inline errors and folds everything else
  (`non_field_errors`, nested errors, fields absent from the form) into the
  returned `detail` → a `topLevelError` alert banner. Don't re-implement that
  fan-out.
- **5xx / network**: `toast.error("Something went wrong")`. Dialog stays open
  on error.
- **Inline zod errors render through `fieldErrorText(t, message)`**
  (`src/lib/forms/fieldError.ts`) — schema messages are i18n keys needing
  translation at render; server text passes through verbatim. Reference:
  `RateCardFormDialog.tsx`. Older dialogs render `String(message)` — retrofit
  when touched.

### Booking money display

The Total / Paid / Due trio always comes from `bookingFinance(booking)`
(`features/bookings/finance.ts`): `total` is the guest-facing **gross**,
`paid` is the backend's `amount_paid`, `due = total − paid`. **Never derive
Paid by subtracting two other fields** — `total − balance_due` once rendered
the agency commission as "Paid €-7,000". Tone Due with
`dueTone(due, balance_due_at)`. Commission only ever appears under an explicit
"Commission" label, never folded into another figure.

### Role gating

`useHasReservationsRole()` (ADMIN, RESERVATIONS, or superuser) gates every
write affordance. **Buttons disable, never disappear** — disabled inside a
Tooltip explaining why. Reference: `BookingActions.tsx`, `PeopleTab.tsx`.

### Dialog mounting

Gate dialogs behind their open state (`{open && <Dialog />}`) so form state
and mutation hooks aren't instantiated for every closed dialog in a list.

### Error differentiation in detail pages

On detail fetch failure, branch on `query.error instanceof ApiError` +
`status`: 404 → "not found", no retry; other → generic error with retry.
Reference: `PropertyDetailLayout.tsx`.

### Internationalization (i18n)

react-i18next app-wide. **Plain user-facing string literals are banned** —
everything goes through `t()`, no exceptions for "obvious" copy. Keys are
nested (`actions.*`, `fields.*`, `errors.*`, …) under one namespace per
feature plus `common`, in `src/i18n/locales/<lang>/<namespace>.json`.
Interpolate, never concatenate; never build a key from input unless it's a
typed enum value; Zod messages are i18n keys. Enum values, query keys, routes,
test IDs, `throw`/`console` strings, and the `"Villa Collective"` brand stay
literals. Full reference: `src/i18n/README.md`.

### Slug safety

Some property `slug` fields contain full URLs. When navigating by slug,
reject any value containing `/` and fall back to the numeric `id`.
Reference: `PropertiesListPage.tsx:handleRowClick`.

### Theming

All visual decisions are CSS custom properties in `src/styles/globals.css`,
exposed to Tailwind via `@theme inline`. Components consume token utilities
(`bg-primary`, `text-success`, `font-serif`, `shadow-card`) — **never raw
Tailwind colour utilities** (`bg-emerald-500`). If a status doesn't fit an
existing tone, add it to `globals.css` + `src/styles/tokens.ts` first.
Page-level h1/h2 use `font-serif`; section/tab headings stay sans. shadcn
primitives in `components/ui/` are left alone (already token-driven). Card
surfaces use `shadow-card`; popovers/dialogs use `shadow-popover` /
`shadow-modal`. Full token list + rebrand walkthrough:
`src/styles/README.md`; typed `var(--…)` helpers in `src/styles/tokens.ts`.

## Testing

- **`renderWithProviders`** (`test/render.tsx`): QueryClientProvider +
  MemoryRouter + TooltipProvider; pass `route` for initial URL.
- **`drfPage(rows)`** (`test/drf.ts`): wraps rows in DRF's paginated envelope.
- **MSW**: `test/msw/server.ts`; override handlers per-test with
  `server.use(...)`.
- Test the error split in dialog tests: 4xx → inline field errors, 5xx →
  toast.
- **Agents — keep captured output lean.** Run `npm run test:agent`
  (`vitest run --reporter=dot`): a compact dot line + totals instead of the
  default reporter's ~200 per-file lines, failure detail still printed. Never
  run bare `npm test` or `npm run test:watch` — both start **watch mode and
  hang**; only `test:run`/`test:agent` exit.

## Component library

shadcn/ui primitives in `components/ui/` (leave alone). Custom shared
components: `components/data/` (DataTable, FactList, StatusBadge, StagePips,
Toolbar, Section, ServiceDot, TierBadge), `components/feedback/`
(ConfirmDialog, EmptyState, ErrorState, QuickActions, ComingSoonTab),
`components/layout/` (AppShell, PageHeader, TwoColumn).

## Routing

Detail pages use a layout component with `<Outlet context={{ entity }} />`;
tabs consume via `useOutletContext()`. Unimplemented tabs render
`ComingSoonTab`. Reference: `PropertyDetailLayout.tsx`.
