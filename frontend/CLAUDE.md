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

### Zod-first types

Every API response type is derived from a Zod schema
(`z.infer<typeof schema>`), never hand-typed. Write-input schemas live
in the same `schemas.ts` and power `zodResolver` in forms. The API layer
parses every response through the schema before returning it.

### API client

`apiGet` for reads, `apiSend` for writes. Both live in
`lib/api/client.ts`. Always call as `apiGet<unknown>(path)` and parse
the result with a Zod schema — never trust the raw response type.

Custom actions use colon-verb syntax: `POST /bookings/{id}:confirm`,
`POST /contacts/{id}/emails/{id}:set-primary`.

### React Query

- **Query keys**: factory in `lib/query/keys.ts`. Nest detail
  sub-resources under their parent: `["properties", "detail", id, "contacts"]`.
- **Conditional queries**: `enabledQuery(id, keyFor, fetchFor)` returns a
  disabled query when `id` is undefined. Use it for any hook where the
  parameter might not be available yet.
- **Mutations**: invalidate the narrowest relevant query key on success.
  Use `queryClient.invalidateQueries` — don't manually update cache
  unless optimistic UI is needed (see `useToggleNotePin` for the one
  optimistic example).
- **Auth boundaries wipe the whole cache.** Login, 2FA verify, logout, and
  the boot-level 401 handler all funnel through `resetAuthQueryCache`
  (`features/auth/resetAuthQueryCache.ts`) — never a hand-picked prefix
  allowlist, which would leak one user's cached data into the next session.
  Any new auth transition (password reset, account switch) must call it too.

### Form dialog pattern (create / edit)

Discriminated union props: `{ mode: "create" }` | `{ mode: "edit"; entity: T }`.
Each dialog is a self-contained component — no shared form dialog
abstraction. The template is `NoteFormDialog.tsx`.

- Reset form state in a `useEffect` gated on `open`.
- **4xx field errors**: `applyApiErrorToForm(form, error)` maps matched
  `field_errors` to RHF inline errors, and folds everything without an
  inline home — `non_field_errors`, nested serializer errors, and fields
  absent from the form — into the returned `detail`, which goes to a
  `topLevelError` state shown as an alert banner. Don't re-implement that
  fan-out at the call site.
- **5xx / network errors**: `toast.error("Something went wrong")`.
- Dialog stays open on error so the user can fix and retry.
- **Inline zod errors render through `fieldErrorText(t, message)`**
  (`src/lib/forms/fieldError.ts`) — schema messages are i18n keys and need
  translating at render; server text passes through verbatim. Reference:
  `RateCardFormDialog.tsx` / `RateRuleFormDialog.tsx`. Older dialogs still
  render `String(message)` and show raw keys — retrofit when touched.

### Role gating

`useHasReservationsRole()` returns true for `ADMIN`, `RESERVATIONS`, or
superuser. Gate every write affordance (button, menu item) on this hook.

**Buttons disable, never disappear.** When the user lacks the role, the
button renders disabled inside a Tooltip explaining why. Reference:
`BookingActions.tsx`, `PeopleTab.tsx`.

### Dialog mounting

Gate dialog components behind their open state (`{open && <Dialog />}`)
so form state and mutation hooks are not instantiated for every closed
dialog in a list.

### Error differentiation in detail pages

When a detail page fetch fails, check `query.error instanceof ApiError`
and branch on `status`:

- **404**: show "not found" with no retry.
- **Other**: show a generic error with a retry button.

Reference: `PropertyDetailLayout.tsx`.

### Internationalization (i18n)

react-i18next is wired up app-wide. **Plain user-facing string literals
are banned** — every user-facing string goes through `t()`, no exceptions
for "obvious" copy or short button text. Keys are nested
(`actions.*`, `fields.*`, `errors.*`, `empty.*`, `toasts.*`,
`placeholders.*`) under one namespace per feature, plus `common`, and live
in `src/i18n/locales/<lang>/<namespace>.json`.

Three rules worth pinning here: interpolate, never concatenate
(`t("rail.party", { adults })`, not `` `${adults} adults` ``); never build
a key from interpolated input unless the fragment is a typed enum value;
Zod messages are i18n keys, not English. Enum values, query keys, route
paths, test IDs, `throw`/`console` strings, and the `"Villa Collective"`
brand stay literals.

Full reference — the complete covered/allowed lists, the add-a-string
workflow, locale source of truth, and how to add a language — lives in
`src/i18n/README.md`.

### Slug safety

Some property `slug` fields contain full URLs instead of simple slugs.
When navigating by slug, reject any value containing `/` and fall back
to the numeric `id`. Reference: `PropertiesListPage.tsx:handleRowClick`.

### Theming

All visual decisions live in `src/styles/globals.css` as CSS custom
properties, exposed to Tailwind via `@theme inline`. Components consume
_token utilities_ (`bg-primary`, `text-success`, `font-serif`,
`shadow-card`), never raw Tailwind colour utilities (`bg-emerald-500`,
`text-amber-700`). Re-skinning is a one-file edit.

Token layers (low → high):

1. **Ramps** — `--brand-*`, `--accent-*`, `--neutral-*` (OKLCH).
2. **Semantic surfaces** — shadcn (`--primary`, `--card`, …) wired to the
   ramp; plus `--background` (a subtle neutral wash so cards lift).
3. **Status tones** — `--status-{success|warning|danger|info|neutral|hold}`.
4. **Categorical palettes** — `--svc-*` (13 concierge service colours),
   `--lead-*` (Hot/Warm/Cold/Dead), `--tier-*` (Quintessential/Signature),
   `--nav-active` / `--nav-hover` (soft brand wash for sidebar).
5. **Typography** — Fraunces (serif, page headings) + Geist (sans, body).

Reference docs / files:

- `src/styles/README.md` — full token list + rebrand walkthrough.
- `src/styles/tokens.ts` — typed `var(--…)` helpers for data-driven
  palettes (e.g. `serviceColorVar["chef"]`).
- `components/data/StatusBadge.tsx` — semantic status pill.
- `components/data/ServiceDot.tsx` — concierge service colour + state.
- `components/data/TierBadge.tsx` — Q / S tier badge.

Rules:

- **No raw Tailwind colour utilities** (`bg-red-500`, `text-emerald-700`).
  If a status doesn't fit an existing tone, add the tone to `globals.css`
  and `tokens.ts` first.
- **Page-level h1/h2 use `font-serif`**; section/tab headings stay sans.
- **shadcn UI primitives** in `components/ui/` are left alone — they
  already read from semantic tokens.
- **Feature-level card surfaces** use `shadow-card`; deeper elevation
  (popovers, dialogs) uses `shadow-popover` / `shadow-modal`.

## Testing

- **`renderWithProviders`** (`test/render.tsx`): wraps component in
  QueryClientProvider + MemoryRouter + TooltipProvider. Pass `route` for
  initial URL.
- **`drfPage(rows)`** (`test/drf.ts`): wraps an array in DRF's
  paginated envelope (`{ count, next, previous, results }`).
- **MSW**: `test/msw/server.ts` sets up before/after hooks. Override
  handlers per-test with `server.use(...)`.
- Test the error split: 4xx → inline field errors, 5xx → toast. Test
  both in dialog component tests.

## Component library

shadcn/ui primitives live in `components/ui/`. Custom components:

- **`components/data/`**: `DataTable`, `FactList`, `StatusBadge`,
  `StagePips`, `Toolbar`, `Section`.
- **`components/feedback/`**: `ConfirmDialog`, `EmptyState`, `ErrorState`,
  `QuickActions`, `ComingSoonTab`.
- **`components/layout/`**: `AppShell`, `PageHeader`, `TwoColumn`.

## Routing

Detail pages use a layout component with `<Outlet context={{ entity }} />`
and tab sub-routes. Tabs consume context via `useOutletContext()`.
Unimplemented tabs render `ComingSoonTab`. Reference:
`PropertyDetailLayout.tsx`, `BookingDetailLayout.tsx`.
