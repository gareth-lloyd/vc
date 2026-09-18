# GAP-117 — `/bookings` has no "Imported bookings" tab (imported `PastStay` rows are only reachable per client)

> **✅ RESOLVED (2026-09-18, local main unpushed)** — 4 code units on
> `feat/gap-117`:
> - **Endpoint:** a staff-only, read-only `GET /api/v1/past-stays`
>   (`PastStayListView`, `reservations/views/past_stays.py`).
>   - It uses `PastStayListSerializer`, which is `ContactPastStaySerializer`
>     plus `person` and a nullable `person_name`.
>   - `?search=` matches the guest's first and last name, `villa_name`,
>     the property's name and display name, and `booking_number`.
>   - `?ordering=` is disabled. The order is `Meta.ordering` plus a `pk`
>     tie-break, so paging across clients is stable.
>   - The query count is pinned at 4.
>   - A test pins that an app `Booking` never appears.
> - **Shared row code:** the row schema and formatting moved to
>   `frontend/src/lib/domain/importedBooking.ts`.
> - **Relabel:** the client-profile accordion and the RepeatBadge count now
>   read "Imported bookings" (el "Εισαγόμενες κρατήσεις"). Only the values
>   changed; the keys did not.
> - **Tab:** `/bookings` has Radix tabs driven by `?tab=imported`.
>   - Switching tab pushes a history entry and clears the other tab's params.
>   - Arrow keys only move focus (manual activation).
>   - Only the active tab mounts.
>   - `ImportedBookingsTab` has search, server pagination and no sort.
>     Guest links go to `/clients/:id/details` ("Unnamed client" when the name
>     is blank); villa links go to `/properties/:id`, or show the sheet name.
>
> **Deviations from the proposal below:**
> 1. The shared code lives in `lib/domain/importedBooking.ts`, not
>    `features/contacts/…`. eslint-boundaries forbids `bookings → contacts`
>    and accepts no new edges. `contacts/schemas.ts` re-exports the schema
>    under its old `contactPastStay*` names.
> 2. The URL is `/api/v1/past-stays` (the v1 mount, no trailing slash).
> 3. The query key is `queryKeys.importedBookings.list`.
> 4. The i18n block is `bookings:list_tabs.*` because `tabs.*` is already
>    used by the booking detail tabs.
> 5. RepeatBadge's "N past stays" count was relabelled too.
>
> **Accepted:** the new key is not invalidated on contact merge or
> anonymise. A stale row lasts at most the global staleTime.
>
> **Deferred:** extra filters and sorting, CSV export, and a row detail page.

- **Severity:** 🟡 Gap (frontend + one small read endpoint). The data is
  loaded and shown per client; there is no cross-client list.
- **Source:** owner request, 2026-09-18 — a simple tab on the /bookings view
  listing the imported historic bookings, re-using the customer-profile
  display, as a paginated list.
- **Files touched (when built):**
  - `django_res/reservations/views/contact_reads.py` — `past_stays` is the
    per-contact read (`/contacts/{id}/past-stays`); the new list endpoint sits
    beside it or in its own small viewset.
  - `django_res/reservations/serializers/contact.py` —
    `ContactPastStaySerializer` (reuse; subclass to add the guest).
  - `django_res/reservations/urls.py` — register `/past-stays`.
  - `django_res/reservations/models/past_stay.py` — docstring only (see
    Nomenclature).
  - `frontend/src/features/bookings/BookingsListPage.tsx` — add the tab.
  - `frontend/src/features/contacts/components/ContactPastStayHistory.tsx` —
    the display to reuse (row rendering + `recordedAmount`).
  - `frontend/src/features/contacts/schemas.ts` (`contactPastStaySchema`),
    `frontend/src/lib/query/keys.ts`, `frontend/src/i18n/locales/{en,el}/`.

## Nomenclature

**"Imported bookings"** = stays loaded from the legacy system at cutover —
Nick's spreadsheets (`import_past_bookers`) and legacy `VillaArchiveBookings`
(`import_archive_stays`) — stored as `PastStay` rows. **Nothing created in
the new system is ever an imported booking**, however far in the past it is:
a finished `Booking` stays a `Booking` and is listed on the Bookings tab
(via its status filter / check-out dates), never on the Imported tab.

This is a UI/ticket naming decision only. **No model, table, field or
endpoint rename** — `PastStay`, `/contacts/{id}/past-stays` and the importers
keep their names. Where the code name and the UI name diverge, a comment says
so:

- `PastStay` module docstring: state that rows are created **only** by the
  two cutover importers, never by the app, and are shown in the UI as
  "Imported bookings".
- The new endpoint / serializer docstring and `ContactPastStayHistory`'s
  doc comment: same one-line pointer.

## Problem

Historic stays imported from the legacy data land as `PastStay` rows, never
`Booking`s (GAP-089, GAP-113). They are visible only inside one client's
profile — the `ContactPastStayHistory` accordion on `/clients/:id/details`
and in `CustomerProfilePanel`. `/bookings` lists `Booking` rows only, so
there is no place to browse imported bookings across clients, or to find one
by villa or legacy booking number without first knowing the guest.

## Proposed fix

Keep it simple — a read-only list, no editing, no filters beyond search.

**Backend.** `GET /api/past-stays/` — staff-only (`IsStaff`, same as the
contact reads), DRF-paginated with the project default page size, ordered by
the model `Meta` (newest year, then newest `date_from`). Serializer =
`ContactPastStaySerializer` fields + `person` (pk) + `person_name`.
`select_related("person", "property", "currency")` — pin the query count in a
test (SMELL-011). Optional `?search=` over guest name, `villa_name`,
`property__name`, `booking_number` via DRF `SearchFilter` (off-the-shelf; no
bespoke filter set). Reads `PastStay` only — no union with `Booking`.

**Frontend.**
- Tabs on `BookingsListPage`: **Bookings** (today's page, unchanged) |
  **Imported bookings**. Drive the active tab from the URL
  (`?tab=imported`) so it survives reload and back-navigation; the existing
  filter params apply to the Bookings tab only.
- Imported tab = `DataTable` (the component the bookings list already uses
  for pagination) with columns: guest (links to `/clients/:id/details`),
  villa (links to `/properties/:id` when `property` resolved, else the raw
  `villa_name`), destination, dates-or-year, legacy booking number, amount
  as recorded.
- **Reuse, don't copy:** lift the per-row formatting out of
  `ContactPastStayHistory` — `recordedAmount()`, the dates-or-year fallback,
  the property-link-or-villa-name cell — into a small shared module
  (e.g. `features/contacts/importedBookingFormat.tsx`) consumed by both the
  accordion and the new columns. The accordion's shell (collapsible,
  first-page-only, "N more" hint) is not reusable for a paginated list and
  should not be forced into one.
- Reuse `contactPastStaySchema` via `.extend({ person, person_name })`; new
  `queryKeys.pastStays.list(filters)`.
- **Relabel the customer-profile accordion** from "Past stays" /
  "Προηγούμενες διαμονές" (`contacts.profile.stays_*`) to "Imported
  bookings" (+ el), so the same rows carry the same name in both places.
  Label-only; translation keys may stay as they are.
- en + el strings for the tab, columns and empty/error states.

## Acceptance

- Backend: pytest for the list endpoint — staff-only (401/403 for anon /
  non-staff), paginated shape, ordering, `person_name` + `property_name`
  present, `currency_code` null when legacy recorded none, search hits on
  guest / villa / booking number, pinned query count, and a completed
  `Booking` for the same guest does **not** appear.
- Frontend: vitest — the tab switch is URL-driven; the imported tab renders
  rows with guest and villa links, dates-vs-year fallback and
  amount-as-recorded; pagination requests `?page=N`; loading / empty / error
  states; `ContactPastStayHistory` tests stay green after the formatting lift
  (updated for the new label).
- No migration generated (`makemigrations --check` clean).
- Quality gate green (ruff, mypy, eslint, prettier, tsc).

## Dependencies

- Builds on GAP-089 / GAP-113 (resolved) — `PastStay` model, importers,
  per-contact endpoint.
- None blocking.
