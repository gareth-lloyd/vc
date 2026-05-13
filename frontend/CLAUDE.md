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

### Slug safety

Some property `slug` fields contain full URLs instead of simple slugs.
When navigating by slug, reject any value containing `/` and fall back
to the numeric `id`. Reference: `PropertiesListPage.tsx:handleRowClick`.

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
