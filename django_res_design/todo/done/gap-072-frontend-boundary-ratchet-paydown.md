> **✅ RESOLVED (2026-07-06)** — shipped on local `main` (ff `fbf6263`,
> unpushed; work commits `fdfad2b`, `45ef467`, `c43bc0e`, `218a9a0`,
> `a25658d`). Both mutual UI cycles are gone: `contacts→properties` broke by
> lifting `PROPERTY_CONTACT_ROLES` to `lib/domain/contactRoles`, and
> `enquiries→quotations` broke by injecting `QuoteBuilder` as a route-level
> slot (`quoteBuilder` prop on `EnquiryDetailLayout`, composed in
> `app/router.tsx`) — `quotations→enquiries` stays as the sanctioned
> downstream direction. Geo/taxonomy read side (schemas, list fetchers,
> `useRegions`/`useCollections`/`useCountries`, `regionOptionsForCountry`,
> `TAXONOMY_PAGE_SIZE`) promoted to `src/lib/geo/`; country CRUD stays in
> `admin/countries`; old feature homes re-export shims for intra-feature
> callers. Two bonus one-symbol edges killed (`PERSON_TAGS`,
> `bookingStatusLabel` → `lib/domain`). The allowlist is now **tiered**:
> `SANCTIONED_EDGES` (18, stable architecture) + `DEBT_EDGES` (2, shrink-only:
> `enquiries→bookings` ReasonFormDialog, `quotations→bookings`
> bookingDetailSchema pending GAP-062) merged into `ALLOWED_EDGES` that eslint
> consumes unchanged. `boundaries.test.ts` gained per-tier liveness +
> tier-disjointness + union checks. **20 edges total, zero mutual pairs**, debt
> tier of 2 (was 27 flat). Deferred (recorded, not done): `properties→contacts`
> people-management (8 imports, tiered SANCTIONED); re-homing `EnquiryDetail`
> and `bookingDetailSchema` into `lib/domain` (GAP-062 codegen territory).
> Frontend gate green: 1814 vitest passing, tsc/eslint/prettier clean.

# GAP-072 — Pay down the remaining frontend boundary-ratchet edges (2 cycles + the sanctioned-edge tier)

- **Severity:** Gap (frontend architecture, debt pay-down) — the boundary
  contract shipped in GAP-063; this is the residue it deliberately deferred.
- **Source:** GAP-063 close-out (2026-07-05). The ratchet
  (`frontend/boundaries.allowlist.js`) froze 27 cross-feature pairs; every
  entry is now explicit, shrink-only, and liveness-tested
  (`src/test/boundaries.test.ts`) — but 27 edges is still coupling, and two
  of them still form mutual cycles.
- **Files:**
  - `frontend/boundaries.allowlist.js` (the full edge list).
  - properties⇄contacts cycle: `properties/*` → contacts (~8 imports:
    PeopleTab, contact pickers) vs `contacts/schemas.ts` /
    `contacts/components/*` → properties (1 import).
  - enquiries⇄quotations UI cycle: `enquiries/EnquiryDetailLayout.tsx:23`
    (QuoteBuilder embed) vs quotations → enquiries (~5 imports:
    `searchCriteria.ts`, `SaveQuoteDialog`, `QuoteBuilder`,
    `EnquirySummaryHeader` — type-only `EnquiryDetail` mostly).
  - Geo/taxonomy split: `useRegions`/`useCollections` live in
    `properties/hooks.ts` (consumed by availability, clients, quotations via
    allowlisted edges); `useCountries` lives in `admin/countries/hooks.ts`.

## Problem

GAP-063 broke the four schema-level cycles and established the contract, but
deliberately deferred:

1. **properties⇄contacts** — the last remaining two-way feature cycle.
   Neither side can be moved or tested in isolation.
2. **enquiries⇄quotations at the UI level** — the schema cycle is dead
   (read-model lives in `src/lib/domain/quotation.ts`), but the QuoteBuilder
   embed keeps the pair mutual. A quote is downstream of its enquiry; the
   reverse edge is the anomaly.
3. **No "permanent vs debt" tier on the allowlist.** Several one-way edges
   look like acceptable architecture, not debt — `*→audit` (5 features embed
   the audit-trail widget), `*→users` (user pickers), `*→admin` (taxonomy
   hooks). Leaving them indistinguishable from real debt means the ratchet's
   size never becomes a meaningful health metric, and nobody knows which
   entries are supposed to shrink.
4. **Geo taxonomy has two homes** (flagged in GAP-063 Unit 3 review):
   regions/collections under properties, countries under admin. The first
   feature outside the current allowlist that needs a region picker cannot
   get one without an allowlist addition — which the ratchet forbids.

## Proposed fix

Incremental, one edge-group per commit; each commit deletes (or re-tiers) its
allowlist entries:

1. **Break properties⇄contacts.** The thin direction (contacts→properties,
   1 import) is the cheap kill: lift the shared shape into `src/lib/domain/`
   or invert it. Then decide whether properties→contacts (the 8-import
   direction: people/contact management on the property page) is sanctioned
   downstream coupling — if so, tier it (see 3), don't pretend it will shrink.
2. **Make enquiries⇄quotations one-way.** Move the QuoteBuilder mount out of
   `EnquiryDetailLayout` (route-level composition in `src/app/`, which may
   legally import both features) or accept quotations→enquiries as the single
   sanctioned direction and re-home the embed. Either way the mutual pair
   becomes one arrow.
3. **Introduce a documented allowlist tier split** in
   `boundaries.allowlist.js`: `SANCTIONED_EDGES` (audit widgets, user
   pickers, downstream flows like owner-portal→auth, quotations→enquiries —
   stable, not expected to shrink) vs `DEBT_EDGES` (everything else,
   shrink-only). The staleness vitest covers both; CLAUDE.md wording updates
   so "the ratchet only shrinks" applies to the debt tier.
4. **Decide the geo/taxonomy home** — either promote
   `useRegions`/`useCollections`/`useCountries` (+ fetchers + query keys)
   into a shared `src/lib/` module, or declare properties/admin the permanent
   owners and tier those edges as sanctioned. Decision recorded in
   `frontend/CLAUDE.md`.

## Acceptance

- No mutual (two-way) pairs remain in the measured feature graph.
- Every allowlist entry is tiered sanctioned-or-debt, with the split
  documented in `frontend/CLAUDE.md`; the debt tier is strictly smaller than
  at ticket-open (27 total pairs).
- Geo/taxonomy home decision recorded in `frontend/CLAUDE.md`.
- Quality gate green; staleness vitest still enforces liveness for both tiers.

## Dependencies

- Builds on [GAP-063](done/gap-063-frontend-feature-coupling-and-cycles.md)
  (✅ resolved — contract + first four cycles).
- The `src/lib/domain/` lifts should coordinate with
  [GAP-062](gap-062-frontend-schema-contract-drift-no-codegen.md) so shared
  shapes are extracted once.
