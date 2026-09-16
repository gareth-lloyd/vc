# GAP-116 — Quote builder does not show the client's tags

> **✅ RESOLVED (2026-09-16)** — shipped on `feat/gap-116`; fast-forwarded into
> local `main` (unpushed) at close-out. 5a253e7b: `EnquirySummaryHeader` reads
> the linked client via `useContact(enquiry.person ?? undefined)` (disabled
> when no person; same query key as the rail's `CustomerProfilePanel`) and
> renders the existing read-only `RepeatBadge` + `TagChips` in its title row,
> as the Proposed fix said. No serializer change, no new import-boundary edge
> (`quotations → contacts` was already sanctioned). Both components return
> `null` when empty, so no person / no tags / first-time customer / loading /
> a failed read add no markup. vitest: tag chips, Repeat badge, no badge for a
> first-time customer, no request without a person (spy handler — MSW's
> `onUnhandledRequest: "error"` does **not** fail a vitest test, so absence
> tests must prove it), no extra markup for an untagged first-timer, header
> intact on a 404 contact read; `QuoteBuilder.test.tsx` gained a contacts
> handler for its linked person. Guest-facing output is untouched:
> `EnquirySummaryHeader` renders only in `QuoteBuilder`. `RepeatBadge` shows
> its "N bookings" count text beside the reference; a compact variant was not
> built (KISS) — revisit only if it reads badly in use.

- **Severity:** 🟡 Gap (frontend). The tags exist and render elsewhere; the
  builder is the one screen where the sales team quotes without them.
- **Source:** Owner request, 2026-09-16 ("show client tags on quote
  builder"). Two resolved tickets left this deferred, and no open ticket
  picked it up:
  - [GAP-040](gap-040-customer-tags-taxonomy.md) banner: "**Deferred:**
    read-only chips on the enquiry/quote client block". The original source
    was the mockup's **New Quote → client block**.
  - [GAP-042](gap-042-customer-360-profile-view.md) banner: "**Deferred:**
    … quote-builder inline embed (no rail)".
- **Files touched (when built):**
  - `frontend/src/features/quotations/components/EnquirySummaryHeader.tsx`:
    the builder's pinned header. It shows guest name, reference, dates,
    party, request type and source, but no tags.
  - `frontend/src/features/contacts/components/TagChips.tsx`: the existing
    read-only chip renderer (GAP-040 F1).
  - `frontend/src/features/contacts/hooks.ts` (`useContact`): already serves
    `tags` on `GET /contacts/{id}`.
  - No backend change expected (see *Proposed fix*).

## Problem (verified against `main`, 2026-09-16)

`QuoteBuilder` has one mount point, inline in the enquiry detail page
(`EnquiryDetailLayout.tsx:214`). Client tags reach that page only through
`CustomerProfilePanel` in the right rail (`EnquiryDetailLayout.tsx:303`).
Opening the builder hides that rail:
`hideRail={building && !isFinalStatus(enquiry.status)}`
(`EnquiryDetailLayout.tsx:298`). So while staff are quoting:

- the rail with the tags is gone,
- the builder's own `EnquirySummaryHeader` renders `guestName(enquiry)` and
  the stay facts, but no tags,
- the page header (`PageHeader`) shows reference + guest name only,
- the enquiry serializer (`reservations/serializers/enquiry.py`) carries
  `person` + `guest_*` fields but no `tags`, so nothing downstream could
  show them either.

The flags the owner wanted "at a glance" when quoting (VIP, Trade,
Approach with care, Disability, …) are therefore hidden exactly when they
matter. The quotation detail page does show them, through its rail
(`QuotationDetailLayout.tsx:391`), but only after the quote exists.

## Proposed fix

Frontend only, reusing what GAP-040/042 built:

- In `EnquirySummaryHeader`, when `enquiry.person` is set, read the contact
  via `useContact(enquiry.person)` and render `<TagChips tags={contact.tags} />`
  next to the guest name. It uses the same query key as the rail's
  `CustomerProfilePanel`, so it is normally a cache hit, not a new request.
- Read-only. Tags stay editable on the profile panel and the Clients list
  (GAP-053's inline editor). Don't add a second editor.
- Also show the derived **Repeat** badge (`is_repeat_customer`, GAP-042),
  as the profile panel does. It comes from the same payload. Owner
  confirmed 2026-09-16.
- No person (`person` null, e.g. an enquiry not yet linked to a customer)
  or no tags: render nothing, no empty placeholder.

The GAP-040 note said this "needs an enquiry/quotation serializer change".
That was true before GAP-042 made the contact read reusable. Adding `tags` to
the enquiry payload is the alternative, but it duplicates data the page
already fetches and would need the special-category erasure handling applied
to a second serializer. Not recommended.

## Acceptance

- With the builder open on an enquiry whose person has tags, the tag chips
  are visible in the builder header (vitest on `EnquirySummaryHeader`, MSW
  contact handler with tags).
- A repeat customer (`is_repeat_customer`) shows the Repeat badge in the
  builder header; a first-time customer does not (vitest).
- No person, or a person with no tags and not a repeat customer: no chips,
  no badge, and no extra empty markup (vitest).
- Tags never reach guest-facing output (`SendPreviewDialog` / quote
  documents). The chips live only in the staff header.
- Frontend quality gate green (`vitest`, `eslint`, `prettier --check`,
  `tsc --noEmit`), including the GAP-072 import-boundary ratchet. The
  `quotations` feature already imports from `contacts` in
  `QuotationDetailLayout`, so no new edge is expected.

## Dependencies

- Builds on **GAP-040** (tags, `TagChips`) and **GAP-042** (`useContact`
  with tags, repeat badge), both resolved.
- Sibling of **GAP-013** (quote-builder UX polish). Independent of it.
