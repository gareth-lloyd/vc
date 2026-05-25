# Frontend — React SPA

Vite + React + TypeScript SPA. shadcn/ui component library, React Query
for server state, React Hook Form + Zod for forms, React Router v6 for
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

### Form dialog pattern (create / edit)

Discriminated union props: `{ mode: "create" }` | `{ mode: "edit"; entity: T }`.
Each dialog is a self-contained component — no shared form dialog
abstraction. The template is `NoteFormDialog.tsx`.

- Reset form state in a `useEffect` gated on `open`.
- **4xx field errors**: `applyApiErrorToForm(form, error)` maps
  `field_errors` to RHF inline errors. Remaining `detail` goes to a
  `topLevelError` state shown as an alert banner.
- **5xx / network errors**: `toast.error("Something went wrong")`.
- Dialog stays open on error so the user can fix and retry.

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
are banned.** Every user-facing string goes through `t()` — no
exceptions for "obvious" copy, single-word labels, or short button text.

This rule covers (non-exhaustive):

- JSX text nodes (`<div>Save</div>` → `<div>{t("actions.save")}</div>`).
- Element attributes that render copy: `placeholder`, `aria-label`,
  `aria-description`, `title`, `alt`, `label`, `description`.
- Toast messages (`toast.success(...)`, `toast.error(...)`).
- Zod schema messages — pass an i18n key string, see "Zod messages" below.
- Validation error fallbacks, empty states, loading states, error states.
- Confirmation dialog titles, bodies, button labels.
- Tooltips, badges, status pips.
- Tab labels — store as `{ slug, labelKey }` objects, never bare strings.
- Page titles, breadcrumbs, section headings.

**Allowed literals** (these are not user-facing copy):

- Brand: `"Villa Collective"` stays a literal.
- Code identifiers: enum values, query keys, route paths, CSS class
  names, test IDs.
- Test assertions: `getByText("Save")` is allowed — the i18n layer
  resolves to English in tests.
- Dev-only strings: `console.warn`, `throw new Error(...)`, debug
  labels, dev-only fallbacks behind `import.meta.env.DEV`.
- API payload fields (request bodies, query params).
- Numeric/symbolic UI atoms with no linguistic content (`"—"`, `"·"`,
  `"#"`).
- Data fixtures and seed values inside `__tests__/` and `test/`.

**When adding a new string**, the workflow is fixed:

1. Pick a namespace — feature namespace by default; `common` only for
   things genuinely reused across features.
2. Add the key to `src/i18n/locales/en/<namespace>.json` under a nested
   path (`actions.*`, `fields.*`, `errors.*`, `empty.*`, `toasts.*`,
   `placeholders.*`, etc.).
3. Use it: `t("actions.save")` (same-namespace) or
   `t("common:actions.save")` (cross-namespace).
4. Never construct a key from interpolated input
   (``t(`status.${value}`)``) **unless** the fragment is a typed
   enum value — that's the only sanctioned dynamic-key pattern, and
   it's documented per feature (e.g. `bookingStatusLabel`,
   `enquiryStatusLabel`).

**Interpolation, not concatenation.** `t("rail.party", { adults })` —
never `` `${adults} adults` ``. Pluralisation uses i18next's native
`_one` / `_other` suffixes: `t("columns.nights", { count: n })`.

- **Locale source of truth**: `User.preferred_language` on the backend
  (exposed via `GET/PATCH /auth/me`). `useLanguageSync` (mounted inside
  `AppProviders`) reflects the authenticated user's value into
  i18next. Anonymous visitors fall back to `localStorage["vc.lang"]`
  then `navigator.language` via i18next-browser-languagedetector.
- **Namespaces**: one per feature plus `common`. Components call
  `const { t } = useTranslation("contacts")` and reach into `common`
  for shared strings (`t("common:actions.save")`).
- **Locale JSON files** live in `src/i18n/locales/<lang>/<namespace>.json`.
  Keys are nested under `actions.*`, `fields.*`, `placeholders.*`,
  `toasts.*`, `empty.*`, `errors.*`. Duplicate strings between features
  rather than reaching across namespaces — translators want each
  feature self-contained.
- **Zod messages are keys, not English**. The error map in
  `src/i18n/zodErrorMap.ts` resolves Zod's default codes against
  `common:zod.*`. For explicit messages on `.min`, `.email`, `.refine`
  etc., pass a fully-qualified i18n key:
  `z.string().min(1, { message: "auth:errors.password_required" })`.
- **Date/number formatting** goes through `src/lib/format/*.ts`. Never
  call `toLocaleString` or `format(...)` directly in components; the
  helpers pick up the active locale.
- **Tests** wrap children in `I18nextProvider` via `renderWithProviders`
  with English loaded. Assertions can target the English copy
  (`getByText("New contact")`) — they exercise the real translation
  layer, not a stub.
- **Adding a language**: drop new JSON files under
  `src/i18n/locales/<lang>/`, extend `SUPPORTED_LANGUAGES` in
  `src/i18n/index.ts`, register a `date-fns` locale in
  `src/lib/format/date.ts`, and add the option to the language picker.

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
5. **Typography** — Fraunces (serif, page headings) + Inter (sans, body).

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
