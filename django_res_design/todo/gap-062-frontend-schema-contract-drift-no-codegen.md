# GAP-062 — No frontend↔backend contract check: 20 hand-maintained Zod schemas drift silently from DRF

- **Severity:** Gap (frontend infra) — a designed-but-unbuilt safety net; the
  mirrors exist, the drift-detection does not.
- **Source:** the 2026-07-02 frontend complexity audit (type/schema layer).
- **Files:**
  - `frontend/src/features/*/schemas.ts` (20 files, ~4,000 LOC of Zod),
    largest: `properties/schemas.ts` (897), `bookings/schemas.ts` (752),
    `quotations/schemas.ts` (535).
  - Concrete live contradiction: `currency` is `z.number()` in
    `bookings/schemas.ts` (`:33,275,295,537,590,657`) and
    `properties/schemas.ts` (`:487,713,754`) but `z.string()` in
    `quotations/schemas.ts` (`:74,226,445`); same split on `country`
    (`z.number()` in `contacts/schemas.ts:66,145` &
    `properties/schemas.ts:298,841` vs `z.string()` in
    `quotations/schemas.ts:103,138`).
  - `frontend/package.json` (no openapi/orval/swagger tooling today).

## Problem

Every response the SPA reads is validated by a **hand-written Zod mirror** of a
DRF serializer. There is no codegen and no contract test, so a mirror only
diverges from the backend at **runtime, in the browser, when a parse throws** —
and for the many loose fields, not even then. Evidence the mirrors already lag:

- **Same concept typed incompatibly across features.** `currency` and
  `country` are `number` in some features and `string` in others (refs above).
  At least one is wrong against DRF; nothing flags it until a user hits the
  offending screen. There is no shared `Money` / `Currency` / `Country` type —
  `amount: z.string()` + `currency` is redeclared inline ~20× in bookings
  alone.
- **Duplicated enums with divergent source-of-truth.** The concierge tier is
  derived from the `TIERS` constant in `concierge/schemas.ts:8` but hardcoded
  `["quintessential","signature"]` in `bookings/schemas.ts:260` — add a tier
  and bookings silently rejects it. `email` is `.email()`-validated in ~5 of
  ~15 declaration sites; the rest accept a bare string.
- **Schemas that have stopped asserting.** `.passthrough()` at
  `bookings/schemas.ts:63,92` and `properties/rate-workbench/schemas.ts:183,193,224`;
  `z.unknown()` for `pricing_snapshot` / `breakdown`
  (`bookings/schemas.ts:136`, `quotations/schemas.ts:75,252`); pervasive
  `.optional()`/`.nullable()` (234 in properties, 149 in bookings). Back-compat
  scars — a dead `rule_id` alias "for pre-SMELL-019 snapshots"
  (`properties/rate-workbench/schemas.ts:177`), renamed-amount tolerance
  (`bookings/schemas.ts:441`) — confirm the mirrors have been patched *after*
  the backend moved, i.e. drift has already bitten and been absorbed.

This is unbuilt safety infrastructure, not a bug in any one schema — hence Gap.

**Drift has since caused a real outage (2026-08-12).** `properties/schemas.ts`
pinned a four-value `z.enum` for `PropertyDescription.section` while the backend
enum had grown to six. `fetchPropertyDescriptions` parses strictly, and
`shouldRetryQuery` (`lib/query/client.ts:28`) returns `false` on a `ZodError`,
so the query landed as `isError` on the first try: **any** property carrying a
`location` or `web_description` row showed "Couldn't load descriptions" with
every section gone — 298 and 276 villas respectively (`COVERAGE.md:109`). It had
been live and unnoticed since those loader sections were added, and read to the
business as "the fields don't exist", generating a request to build them.

Two lessons for the fix above:

- The damage was **whole-response**, not per-field. `paginated()` is a bare
  `z.object` (`lib/api/pagination.ts:3-10`) — one unknown enum value in one row
  takes down every row. A contract test (option 1) would have caught this the
  day the backend enum grew.
- The stopgap applied there is worth copying while this ticket is open: type
  the field as `z.string()` and filter to known values at the component
  boundary, so an unrecognised value degrades to "not rendered". Enum-typed
  fields the SPA doesn't own are the highest-risk shape in the mirrors.

## Proposed fix

Pick one (in rough order of leverage-per-effort):

1. **Contract test (cheapest, no runtime change).** A vitest/pytest bridge that
   runs each feature's response schema against **recorded backend fixtures**
   (DRF `OpenAPIRenderer` output, or captured JSON from the DRF test suite),
   failing CI when a real response no longer parses. Catches the `currency`
   class immediately without adopting codegen.
2. **Generate the response *types* from the DRF OpenAPI schema** (drf-spectacular
   → `openapi-typescript`), and assert the hand-written Zod `infer` matches the
   generated type at compile time. Keeps Zod for runtime validation but pins its
   shape to the backend contract.
3. **Full codegen** (orval / `zod`-emitting) — most invasive; only if 1–2 prove
   the manual mirrors are an ongoing tax.

Whichever is chosen, also: extract a shared `money` / `currencyCode` /
`countryCode` schema into `lib/` and converge the `currency`/`country`
number-vs-string split onto whatever DRF actually returns (fix the real bug the
contract test surfaces).

## Acceptance

- CI fails if a `schemas.ts` response schema cannot parse the recorded backend
  fixture for that endpoint (option 1), or if the generated OpenAPI type and the
  Zod `infer` diverge (option 2).
- The `currency`/`country` number-vs-string contradiction is resolved to a
  single representation matching DRF, expressed once in a shared schema.
- Decision (which option) recorded in `frontend/CLAUDE.md`.

## Dependencies

- Independent of BUG-018 but same audit. The `currency`/`country` fix may touch
  `pricing`/`accounts` serializers if DRF is found to be the inconsistent side.
- Relates to [GAP-063](done/gap-063-frontend-feature-coupling-and-cycles.md)
  (✅ resolved 2026-07-05): the neutral home it proposed now exists —
  `frontend/src/lib/domain/` (holds the quotation read-model and shared
  status enums). The shared `money`/`currencyCode`/`countryCode` schemas
  from this ticket land there.
