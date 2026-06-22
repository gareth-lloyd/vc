# People model cleanup — Enquiry / Guest / Contact

> ✅ **DELIVERED (GAP-045, 2026-06-22).** Contact + `reservations.Guest` are now
> the single `accounts.Person` model (`kind=CUSTOMER/CONTACT`), merged to local
> main. The analysis below is the historical rationale; the live model is in
> `01-accounts.md`.
>
> ⚠️ **SUPERSEDED IN PART (2026-06-18) — unified `Person` identity model.**
> The owner's 2026-06-17 Contacts review drove a domain re-assessment that
> **overturned "Locked decision #1" below** (Guest kept distinct from Contact).
> The direction taken: a **single `Person` identity** absorbs both
> `accounts.Contact` and `reservations.Guest`; capacity (traveller / agent /
> owner / manager / …) is a **role/relationship, never a `kind` column**; a real
> **`Organisation`** entity replaces the free-text `company`; **`User` stays
> first-class** as a login `OneToOne → Person`. The owner's directories
> (Clients / Villa Contacts / Companies) become **filtered views**. This also
> **resolved** the "Guest channel richness" item under *Deferred* (Person carries
> Contact's child email/phone tables). The dedup, contactability-CHECK, and
> E.164 rationale below **still hold** — they moved onto `Person`. Migration was
> tracked by **`todo/gap-045`–`gap-048`**; the decision is logged in
> `10-decisions.md` (2026-06-18). The section below is retained for its
> field-level rationale, read through the lens of this banner.

**Status:** design decision record (2026-06-08), **partly superseded 2026-06-18**
(see banner). Amends `05-reservations.md` (Guest, Enquiry, Quotation) and
references `01-accounts.md` (Contact). Decisions are recorded in
`10-decisions.md`; this doc is the rationale + field-level spec.

**Scope:** data model only. The enquiry→quote *UX* (merged workspace, nav
consolidation, guest search, history) is the GAP-005 "spine UX overhaul" and
rides on top of this — it is **out of scope here**.

## Why

`05-reservations.md` already specifies `Guest` as a *"Unified entity… reused
across enquiries, quotations, and bookings."* The **implementation diverges from
its own spec**: guests are created fresh per quote (a blind `POST /guests` in
`SaveQuoteDialog.tsx`), never deduplicated, and a **synthetic email**
`enquiry-{id}@noemail.local` is fabricated when none is supplied. This record
closes the code↔spec gap and hardens the integrity rules — it does **not** change
the Guest-vs-Contact split (that split is reaffirmed by the existing
`BookingGuest` decision in `10-decisions.md`).

## What legacy does (grounding, not a mandate)

- **Inbound (WordPress)** `POST /api/WordPressApi/Properties/PostEnquire` inserts
  **only** a `VillaEnquire`; email/phone are `NOT NULL` but defaulted to `""`
  (**fake NOT NULL**). No dedup; person data denormalised on the enquiry.
- **Manual path** creates the *quote* and **auto-creates the enquiry** when none
  exists (`sp_quotationMaster`, `@EnquireId=0`). "Every quote has an enquiry" is
  achieved by auto-creation, not a forced capture step.
- **Two person models** — traveller (`VillaClientDetail`, per-enquiry, flat,
  destructive email-upsert) vs agent directory (`VillaContact` + child
  email/phone tables, `IsPrimary`, `PreferredMethod`). The rebuild reproduced
  both: `reservations.Guest` and `accounts.Contact`.
- Legacy ties **required channel to chosen preference** (`ContactType=Email ⇒
  email required`). Kept here as actionable integrity.

## Principles applied

1. One canonical row per real person within its population; events (enquiries)
   reference people, they don't redefine them.
2. Enforce real invariants, not convenient ones — "reachable by ≥1 channel", not
   "has email".
3. No sentinels or synthetics — absence is `NULL`; `NULL` only where absence is
   legitimate. (Kills `enquiry-{id}@noemail.local` and the `Quotation.enquiry`
   nullable-bridge orphan.)
4. Capture-snapshot ≠ identity — an enquiry holds raw captured contact data; the
   Guest is the enforced-clean entity.
5. Preference must be actionable — you can only prefer a channel you've provided.

## Locked decisions

1. **Guest stays the booking-side traveller directory**, distinct from
   `accounts.Contact` (operator CRM). Reaffirms the `BookingGuest` decision.
2. **Identity/dedup = normalized email, then normalized E.164 phone** (adopt
   `phonenumbers`). Dedup is **advisory** (resolve-or-create suggestion +
   operator-confirmed `Guest.merge()`), **not** a hard unique constraint.

## Reconciliation with the existing spec (two corrections)

- **Guest is already specified as "reused"** — so the dedup work *enforces the
  existing spec intent*; it is the implementation that drifted.
- **`email` stays non-unique.** `05-reservations.md` deliberately made email
  non-unique (*"same person legitimately books from different addresses"*), and
  that holds: a person may use several addresses and families share one, so email
  is not a 1:1 identity key. **This supersedes the partial-unique-email index
  floated in the prior plan** — dedup is advisory, not constraint-enforced.

## Field-level amendments

### `reservations.Guest`

| Field / aspect | Now | Change |
|---|---|---|
| `email` | `CIEmailField(db_index=True)`, non-unique, effectively required | **`null=True`** (optional). Stays non-unique. No synthetic fabrication. |
| `phone` | `CharField(blank=True)`, free-text | Store **normalized E.164** (`phonenumbers`) on save; the dedup key. Raw entry preserved if useful. |
| `contact_method` | `TextChoices(EMAIL/PHONE/SMS), null=True` | Unchanged shape; now **constraint-enforced** (below). |
| `anonymize()` | sets `email="redacted-{id}@anonymized.local"` | set **`email=NULL`** (drops another synthetic; `status=ANONYMIZED` already marks the row, reporting filters on `status`). |

**New constraints (the honest NOT-NULLs)** — **scoped to `status=ACTIVE` rows
only**. `ARCHIVED`/`ANONYMIZED` are exempt, which is what lets a channel-less
historical row be *dispositioned* (`status=ARCHIVED`) instead of failing the
constraint (see migration triage). Both `ARCHIVED` and `ANONYMIZED` must be
exempt — `ARCHIVED` is the truthful disposition for "we never captured a
channel"; `ANONYMIZED` would wrongly redact a guest's name.

- **Contactability** — `email IS NOT NULL` **OR** `phone <> ''`. Email is now
  nullable; phone uses blank `''` (not NULL). Encode as
  `CheckConstraint(~Q(status='ACTIVE') | Q(email__isnull=False) | ~Q(phone=''))`.
- **Actionable preference** — `contact_method=EMAIL ⇒ email IS NOT NULL`;
  `contact_method IN (PHONE, SMS) ⇒ phone <> ''` (legacy `ContactType` parity);
  same ACTIVE-only scope.

**Dedup mechanics:** replace the blind `POST /guests` create with a
resolve-or-create that *suggests* a match on normalized email → normalized phone;
the operator confirms reuse (link the existing Guest) or proceeds as new. No
silent auto-merge. Collapsing confirmed duplicates uses the existing
`Guest.merge()`.

### `reservations.Enquiry`

- Keep the denormalised `first_name/last_name/email/phone` snapshot
  (blank-allowed) — the raw inbound capture for unresolved web leads.
- **Add `contact_method`** — `TextChoices(EMAIL/PHONE/SMS), null=True`, mirroring
  the snapshot pattern so a stated preference survives before a Guest exists;
  carried onto the Guest on resolve.
- `guest` FK stays `SET_NULL, null=True` (inbound web = unresolved).
- **No contactability constraint on the raw enquiry** — spam/partial leads are
  real; the enquiry is the permissive capture surface, the Guest is the
  enforced-clean entity. Triage promotes snapshot → Guest.
- Auto-created enquiries (below) are tagged via the **existing `site_source`**
  enum (`AGENT_PORTAL`/`PHONE`/etc.) — no new origin field — so conversion
  reporting (measured per `Enquiry`) can segment them.

### `reservations.Quotation`

- `guest` — **unchanged**: `PROTECT`, required. ✓ correct and legacy-parity.
- `enquiry` — **amended**: `SET_NULL, null=True` → **`PROTECT, null=False`**.
  Satisfied by **auto-creating a minimal enquiry in the quote-creation service
  when none is supplied** (mirrors legacy `sp_quotationMaster`) — no sentinel, no
  nullable-bridge orphan, no forced separate capture step. This **reverses** the
  current line *"quotations can be created agent-direct without an enquiry"*.
  Migration: backfill-audit + back-create enquiries for existing
  `enquiry IS NULL` quotations before tightening.
- `agent` — unchanged (`accounts.Contact PROTECT, null=True`); client + agent
  coexist.

### `reservations.Booking`

No change beyond the Guest cleanups flowing through. The booking-side person model
is `BookingGuest` (existing decision); `Booking.guest` remains the denormalised
LEAD pointer.

### `accounts.Contact`

Unchanged — the agent/owner CRM directory and the *reference shape* Guest is
cleaned toward, but not merged into.

## Cross-cutting / migration (data-model only)

- **`phonenumbers`** dependency (off-the-shelf, CLAUDE.md §2). One-time E.164
  normalization migration of existing `Guest.phone`/`Enquiry.phone`; the
  `data_migration` `GuestLoader` normalises on import (replacing the crude
  `+{cc} {number}`).
- **Legacy import dedup:** no auto-merge by email (agency catch-all + shared
  family addresses). Produce a duplicate-candidate report; collapse via
  `Guest.merge()` under human confirmation. **Evidence:** the in-repo
  demo dump's 135 enquiries collapse to **27 distinct emails**
  (`nick@villacollective.com` ×18, `dev_mojom@gmail.com` ×16) — staff/test
  catch-alls cluster exactly as the no-auto-merge decision anticipates.

### Migration order — triage gates the constraint add

The `@noemail.local` scrub and the new contactability CHECK interact: scrubbing a
synthetic email to `NULL` on a row that has no phone leaves it channel-less, which
the CHECK rejects. Sequence the migration so the constraint is added **after**
triage, and scope each step to its true population:

1. **Scope the scrub to rebuild-created rows only.** `enquiry-{id}@noemail.local`
   is a **rebuild invention** (written by `SaveQuoteDialog.tsx`). Legacy never
   fabricates it — `VillaClientDetail` stores a real `NULL` email and
   `VillaEnquire` stores `""` — so `GuestLoader` imports produce `NULL`/`""`,
   never the synthetic. The scrub pass (`@noemail.local` → `NULL`) targets the
   Postgres backlog the rebuild already wrote; **do not** add a `@noemail.local`
   scan to the legacy import path (it matches nothing there).
2. **Disposition channel-less rows before tightening.** After the scrub, any
   `Guest` with `email IS NULL` **and** `phone IN (NULL, '')` cannot satisfy
   contactability (it had a synthetic email *because* it had no real channel).
   Set `status=ARCHIVED` on these (the honest disposition — exempt from the
   ACTIVE-only constraint), rather than letting the constraint-add migration fail.
3. **Then** add the `CheckConstraint`s.

**Quantify against the prod snapshot first.** The in-repo dump
(`ResSystem/Database/DbScript.sql`) is a dev/demo seed (4 `VillaClientDetails`,
135 `VillaEnquire`, **zero** channel-less rows, zero actionable-preference
violations) — schema-authoritative but **not** prevalence-authoritative. The real
~96 MB prod snapshot loads separately; run the channel-less + preference-mismatch
counts against it before sizing the triage. `VillaClientDetail` allows `NULL`
email **and** `NULL` phone, so channel-less guests are schema-legal in legacy and
may exist in prod even though the demo dump has none.

- **Remove** the `enquiry-{id}@noemail.local` fabrication in
  `frontend/.../quotations/components/SaveQuoteDialog.tsx` — with optional email +
  contactability check, a phone-only guest is a first-class valid row.
- **Enquiry side is safe by design.** Channel-less web leads land as `""`/`""` on
  `Enquiry` (which carries **no** contactability constraint — it's the permissive
  capture surface), so they import fine; only the *Guest* promotion needs triage.

## Deferred (note, don't build)

- Contract identity *snapshot* (name/email as-quoted on Quotation/Booking) for
  audit independence from later merges — rely on `PROTECT` + merge-follows-FK for
  now.
- Guest channel richness: single email+phone (KISS, recommended) vs multi-channel
  child tables like `Contact`.

## Verification (when implemented)

- Migration tests: contactability CHECK rejects an `ACTIVE` guest with neither
  email nor phone but allows an `ARCHIVED` or `ANONYMIZED` one (the dispositioned
  channel-less rows); actionable-preference CHECK rejects an `ACTIVE`
  `contact_method=EMAIL` row with no email.
- Dedup: resolve-or-create surfaces the existing Guest for a repeat normalized
  email/phone; **no `@noemail.local` rows exist** post-change.
- `Quotation.enquiry` is non-null for all rows; quote-create with no enquiry
  auto-creates one tagged via `site_source`.
