# Internationalization (i18n)

react-i18next is wired up app-wide. **Plain user-facing string literals are
banned** — every user-facing string goes through `t()`. This file is the
detailed reference; the short rule lives in `frontend/CLAUDE.md`.

## What the rule covers (non-exhaustive)

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

## Allowed literals (not user-facing copy)

- Brand: `"Villa Collective"` stays a literal.
- Code identifiers: enum values, query keys, route paths, CSS class names,
  test IDs.
- Test assertions: `getByText("Save")` is allowed — the i18n layer resolves to
  English in tests.
- Dev-only strings: `console.warn`, `throw new Error(...)`, debug labels,
  dev-only fallbacks behind `import.meta.env.DEV`.
- API payload fields (request bodies, query params).
- Numeric/symbolic UI atoms with no linguistic content (`"—"`, `"·"`, `"#"`).
- Data fixtures and seed values inside `__tests__/` and `test/`.

## Adding a new string (fixed workflow)

1. Pick a namespace — feature namespace by default; `common` only for things
   genuinely reused across features.
2. Add the key to `src/i18n/locales/en/<namespace>.json` under a nested path
   (`actions.*`, `fields.*`, `errors.*`, `empty.*`, `toasts.*`,
   `placeholders.*`, etc.).
3. Use it: `t("actions.save")` (same-namespace) or `t("common:actions.save")`
   (cross-namespace).
4. Never construct a key from interpolated input (``t(`status.${value}`)``)
   **unless** the fragment is a typed enum value — that's the only sanctioned
   dynamic-key pattern, and it's documented per feature (e.g.
   `bookingStatusLabel`, `enquiryStatusLabel`).

**Interpolation, not concatenation.** `t("rail.party", { adults })` — never
`` `${adults} adults` ``. Pluralisation uses i18next's native `_one` / `_other`
suffixes: `t("columns.nights", { count: n })`.

## Mechanics

- **Locale source of truth**: `User.preferred_language` on the backend
  (exposed via `GET/PATCH /auth/me`). `useLanguageSync` (mounted inside
  `AppProviders`) reflects the authenticated user's value into i18next.
  Anonymous visitors fall back to `localStorage["vc.lang"]` then
  `navigator.language` via i18next-browser-languagedetector.
- **Namespaces**: one per feature plus `common`. Components call
  `const { t } = useTranslation("contacts")` and reach into `common` for shared
  strings (`t("common:actions.save")`).
- **Locale JSON files** live in `src/i18n/locales/<lang>/<namespace>.json`.
  Keys are nested under `actions.*`, `fields.*`, `placeholders.*`, `toasts.*`,
  `empty.*`, `errors.*`. Duplicate strings between features rather than reaching
  across namespaces — translators want each feature self-contained.
- **Zod messages are keys, not English**. The error map in
  `src/i18n/zodErrorMap.ts` resolves Zod's default codes against `common:zod.*`.
  For explicit messages on `.min`, `.email`, `.refine` etc., pass a
  fully-qualified i18n key:
  `z.string().min(1, { message: "auth:errors.password_required" })`.
- **Date/number formatting** goes through `src/lib/format/*.ts`. Never call
  `toLocaleString` or `format(...)` directly in components; the helpers pick up
  the active locale.
- **Tests** wrap children in `I18nextProvider` via `renderWithProviders` with
  English loaded. Assertions can target the English copy (`getByText("New
contact")`) — they exercise the real translation layer, not a stub.
- **Adding a language**: drop new JSON files under `src/i18n/locales/<lang>/`,
  extend `SUPPORTED_LANGUAGES` in `src/i18n/index.ts`, register a `date-fns`
  locale in `src/lib/format/date.ts`, and add the option to the language picker.
