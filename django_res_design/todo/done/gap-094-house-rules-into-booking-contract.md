# GAP-094 — House rules must flow into the booking contract

> **✅ RESOLVED (2026-09-09, local `main` unpushed)** — shipped on `feat/gap-094`
> in 8 code units + this close-out (890761ab snapshot, 69396a05 leak guards,
> 78c0528f WeasyPrint, 05f2b93c render seam + preview, b95f643c
> `BookingDocument` + private storage + auto-generation, 3757e096 the contract
> email with the PDF attached, 67e98089 the staff API, 5cee997d the FE
> Documents tab). The ticket was filed as blocked on a booking-contract
> surface that did not exist; that surface is what this shipped.
>
> **What exists now.** `Booking.house_rules_snapshot` (TextField, blank) is
> stamped on the first entry to `AWAITING_DEPOSIT` — the definition of
> "confirmed", reached from both `auto_accept()` and `owner_approve()`. Those
> two call `Booking._house_rules_stamp()` and pass the result to `_transition`
> as `extra_updates`, so the **read** (`live_house_rules(property_id)`, the
> sole production reader of `DescriptionSection.HOUSE_RULES`) happens at the
> call site and the **write** lands inside `_transition`'s atomic block, on
> the same `save(update_fields=…)` as the status change. `_transition` itself
> is generic and knows nothing about house rules. `_house_rules_stamp` returns
> `{}` once the column is non-empty, and the status guard inside the lock
> rejects a second confirming transition, so the snapshot is written once.
> Every contract renders from that column, so a property's house rules can be
> edited freely without touching a contract a guest already holds
> (acceptance 2). A `BookingDocument(booking CASCADE, kind, file,
> generated_at, generated_by, sent_to_guest_at)` row is minted per generate
> (history kept, never overwritten); the PDF comes from WeasyPrint via
> `core.pdf.html_to_pdf` over `reservations/templates/reservations/booking_contract.html`.
> Confirmation auto-generates the contract and emails it to the guest with
> the PDF attached (`booking.contract`, comms 0004); staff get
> regenerate/download/resend plus a pre-generate HTML preview on a new
> **Documents** tab. Six staff routes, all `IsAuthenticated +
> IsReservationsWriter`; the five nested ones are double-scoped by
> `booking_pk`, so a document id belonging to another booking 404s:
> `GET /bookings/{id}/documents`, `POST …/documents:generate`,
> `GET …/documents/{doc_id}`, `GET …/documents/{doc_id}:download`,
> `POST …/documents/{doc_id}:send`, and `GET …/documents:preview` (a
> `BookingViewSet` action, no stored document needed). Acceptance 1 and 3 are pinned by tests — the leak guard
> (unit 2) seeds a sentinel rules body and asserts it is absent from the Zoho
> villa payload, the Zoho booking payload, the WordPress intake response, the
> public quote-options serializer and the owner-portal booking serializer.
>
> **Divergences from the spec, all deliberate:**
>
> 1. **Generation is synchronous**, not a queued job, and there is no
>    `/jobs/{id}` surface (spec §2.8). Auto-generation is a plain
>    never-raising function scheduled by `transaction.on_commit`, *not* a
>    `@shared_task` — see the worker note below. Volumes are a handful of
>    contracts a day.
> 2. **Download streams through Django** (`FileResponse`, `Content-Disposition:
>    attachment`) behind the staff permission, rather than answering a signed
>    URL. Uniform across the local filesystem and S3, and no URL to the bytes
>    ever exists.
> 3. **A dedicated private `STORAGES["documents"]` alias**, because the
>    default bucket (`villacollective-images`) is world-readable and unsigned
>    and a contract carries guest PII. Locally it is `BASE_DIR/"private_media"`,
>    deliberately **outside `MEDIA_ROOT`** — `MediaWhiteNoiseMiddleware` serves
>    all of `MEDIA_ROOT` unauthenticated at `/media/`.
> 4. **`sent_to_guest_at` means "handed to the mail pipeline"**, not
>    "delivered" — stamped when the `EmailLog` comes back **`QUEUED` or
>    `SENT`** (`comms/signals.py::_HANDED_TO_MAIL_PIPELINE`). Both are
>    required: under `CELERY_TASK_ALWAYS_EAGER`, which is what staging runs,
>    dispatch happens inside the call and the row comes back `SENT` and never
>    `QUEUED` — a `QUEUED`-only gate would never stamp anything in the only
>    deployed environment. `FAILED`, allowlist-`BLOCKED` and skipped sends
>    leave it null and log `comms.email_skipped`; delivery truth stays on the
>    Comms tab, keyed by `correlation.document_id`.
> 5. **No `BookingEvent` row** for a generate — `BookingEvent` has no `kind`
>    for it, so `generated_at`/`generated_by` plus the `AuditLog` entry are
>    the trail.
> 6. **No idempotency key on `:generate`.** "Always a new row" is the
>    recorded decision and a deliberate regenerate after a correction is
>    indistinguishable from a double-submit; the FE disables the button while
>    the mutation is in flight, and a duplicate is at least visible. It is
>    **not removable**, though — see the deletion gap below.
>
> **⚠️ Deploy blocker — user action.** Create a **private,
> public-access-blocked** S3 bucket for documents, grant the existing AWS keys
> read/write on it, and set **`DOCUMENTS_S3_BUCKET`**. `production.py` reads it
> with **no default** — deliberately, so a forgotten variable breaks loudly at
> boot rather than having `auto_generate_contract` swallow a `ClientError` per
> confirmation and every guest silently get no contract — and `staging.py`
> star-imports `production.py`, so the variable is required on **every** service
> running either settings module, not just a future production one.
> `render.yaml` declares it on `villacollective-api` with `sync: false`, so it
> must be set in the Render dashboard **before** the next deploy or the service
> will not start. One bucket can serve both environments: staging overrides only
> the key prefix (`DOCUMENTS_S3_STORAGE_OPTIONS["location"] = "staging"` vs
> `"production"`), so separate buckets are optional, not required.
>
> **⚠️ There is no Celery worker anywhere.** `render.yaml` deploys
> `settings.staging`, which is `CELERY_TASK_ALWAYS_EAGER`, so today's inline
> generation is correct there. `settings/production.py` has **no** eager flag,
> so if a production service is ever stood up it needs either a real worker or
> that flag — and until then anything written as a `@shared_task` would queue
> to nothing. That is why contract generation is a plain function.
>
> **⚠️ Developers need native libraries.** WeasyPrint links against pango:
> `brew install pango harfbuzz libffi` on macOS (`settings/dev.py` and
> `settings/test.py` set `DYLD_FALLBACK_LIBRARY_PATH` on darwin so cffi finds
> `gobject-2.0`); the Dockerfile and CI install `libpango-1.0-0
> libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core`. Noted in
> `django_res/CLAUDE.md`.
>
> **Two findings worth carrying forward.** (i) `DOCUMENT_READ_ERRORS`
> includes `ClientError`, not just `(OSError, ValueError)`: django-storages
> turns only an HTTP 404 into `FileNotFoundError`, and under this bucket's
> policy (`s3:GetObject` without `s3:ListBucket`) a *missing* key answers
> **403** — so the "someone deleted the object" case that every local test
> exercises as a 404 arrives in production as a `ClientError` and would
> otherwise have 500'd all three read routes. (ii) `EmailService.send`
> dedupes on `(template_key, to, correlation)`, so a staff resend of the same
> document would have been a silent no-op; the receiver resends the existing
> log instead, mirroring `booking_confirmation_resend_requested_handler`.
>
> **⚠️ A document cannot be deleted.** There is no `DELETE` route
> (`BookingDocumentDetailView` is a `RetrieveAPIView`), no admin registration
> and no FE affordance — by design, since these are historical records staff
> must be able to fetch. But it means a double-submitted `:generate` leaves
> two identical contracts on the booking with no supported way to remove one;
> today that needs a direct DB delete. Acceptable while nobody has reported it
> (the row is inert unless someone sends it), and it is the other half of the
> "no idempotency key" decision above — if operators do report duplicates,
> revisit both together.
>
> **Deferred, deliberately:** the other four `BookingDocumentKind` values
> (enum only — the API answers `unsupported_kind`); a `/jobs` surface and a
> Celery worker service; a `BookingEventKind` timeline entry for generation;
> signed-URL download; contract i18n and Greek rendering; showing or editing
> the snapshot on the Overview tab; attaching the contract to the
> `booking.confirmation` email itself; migrating `DamageClaimPhoto` /
> `PropertyImage` to the private alias.

- **Severity:** 🟢 Gap (requirement capture — was deferred until the booking
  contract existed; that surface is now built, see above).
- **Source:** 2026-07-20 Nick screen-recording (`Recording-20260720_134424`,
  reviewed 2026-08-11). Transcript `[02:08–02:35]`, recap `[04:09–04:15]`.
- **Files touched** (line numbers refreshed at close-out):
  - `django_res/properties/enums.py:131` — `DescriptionSection.HOUSE_RULES`
    (the source content; keep it through the GAP-090 enum rewrite — the
    docstring above it now records why that matters).
  - `django_res/data_migration/loaders/properties.py:221` — legacy
    `HouseRules` → `HOUSE_RULES`, already imported. The only **writer** of
    the value; `reservations/models/booking.py::live_house_rules` is the only
    production reader.
  - Booking-contract generation — **did not exist**; built by this ticket.
    As shipped: `django_res/reservations/models/booking_document.py`,
    `services/booking_contract_render.py`, `services/booking_documents.py`,
    `storage.py`, `views/booking_document.py`, `core/pdf.py`, the
    `booking.contract` comms template + receiver, and the FE
    `features/bookings/tabs/DocumentsTab.tsx`.

## Problem

House rules are already modelled and imported, and Nick confirms the field
itself is right — *"house rules is good"*. The requirement is about where the
content goes, and it isn't satisfied anywhere:

> *"This is not to be shown online, but this will come into effect during the
> booking process, and the booking system will effectively pull the house
> rules through to form part of the booking contract."* `[02:18]`

Two constraints fall out, and both are easy to lose:

1. **Never rendered publicly.** House rules must not leak into the villa page
   or the WordPress payload. Note the adjacent design in GAP-091: content that
   *could* belong in house rules but should be public goes in the "other
   information" free text instead — so the split is deliberate and the two
   fields are not interchangeable.
2. **Snapshot at booking, not a live reference.** A contract that renders
   today's house rules would silently rewrite what a guest agreed to when the
   property's rules are later edited. The contract needs the rules **as they
   stood when the booking was confirmed**.

Filed now purely so the requirement survives to the booking-contract work —
this is not actionable until that surface exists.

## Proposed fix

When the booking contract is built:

- Pull `HOUSE_RULES` for the booked property into the contract document.
- **Snapshot the text onto the booking** at confirmation rather than
  referencing the live section, so later property edits can't retroactively
  change an agreed contract.
- Keep house rules out of every public/WP payload — assert it, don't assume
  it.

## Acceptance

- Booking contract renders the property's house rules. (test)
- The rendered text is the snapshot taken at confirmation; editing the
  property's house rules afterwards does not change an existing booking's
  contract. (test)
- House rules appear in no public serializer or WordPress payload. (test)

## Dependencies

- ~~**Blocked on the booking contract / guest-facing document surface**,
  which doesn't exist~~ — unblocked by building it (see above). Related
  deferred guest-facing work: GAP-051 (checkout charge itemisation,
  *"deferred until the guest checkout page exists"*).
- **GAP-090** — keep `house_rules` when the `DescriptionSection` enum is
  rebuilt. **Now load-bearing**, not just tidiness: a rename or row remap
  silently yields contracts with no house rules. GAP-090 carries the warning.
- **GAP-091** — the public counterpart; the "other information" free text is
  where house-rules-adjacent content goes when it *should* be shown.
