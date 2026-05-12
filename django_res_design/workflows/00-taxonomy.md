# Workflow Taxonomy

## What counts as a "workflow"

A workflow is a **discrete job to be done** — a coherent operation with:
- a single trigger (user action, webhook, scheduler tick, internal signal)
- a defined set of inputs (entities + datapoints)
- a deterministic process (read/compute/write/notify)
- one or more observable outputs and side effects

The grain is roughly "one transaction-shaped unit of work that a staff member or external system would describe in a single sentence." Examples:
- *Authenticate user with email and password* — one workflow
- *Send security-deposit reminder email* — one workflow
- *Resync property images to WordPress* — one workflow

Loading a list view, opening a page, or rendering UI is **not** a workflow unless it has a non-trivial server-side data shape (e.g., paginated search that fans out to multiple stored procedures).

## File layout

```
workflows/
├── README.md
├── 00-taxonomy.md            ← this file
├── NN-{domain}/
│   ├── README.md             ← domain overview + workflow index
│   └── {topic}.md            ← one or more related workflows
```

Each `{topic}.md` file contains one or more workflows. Tightly-coupled workflows (a CRUD cluster on the same entity) live in one file; substantially different jobs live in their own files.

## Naming convention

### Domain folders
`NN-{domain}` where `{domain}` is a single lowercase noun describing the bounded context. Numbers preserve a reading order, not a dependency order.

### Workflow files
`{topic}-{aspect}.md` — kebab-case, descriptive. Examples:
- `authentication.md`
- `property-master.md`
- `quotation-transmission.md`

### Workflow titles (inside files)
Imperative-mood verb phrase: *"Authenticate user with email and password"*, *"Receive Flywire payment webhook"*, *"Generate three-tier payment schedule"*. Avoid passive voice and avoid the word "handle" (it tells you nothing about what the workflow actually does).

### Workflow IDs
Each workflow has a stable identifier shaped `{DOMAIN}.{TOPIC}.{ACTION}`:
- `IDENTITY.AUTH.LOGIN_PASSWORD`
- `CATALOG.PROPERTY.UPDATE_OVERVIEW`
- `BOOKING.LIFECYCLE.OWNER_CONFIRM`
- `INTEGRATIONS.ZOHO.PUSH_ENQUIRY`

These IDs are stable across renames and serve as cross-references. They map roughly onto event/log names a Django implementation might emit.

## Per-workflow template

Each workflow section uses this template (omit a heading only if it is genuinely N/A):

```markdown
## {Verb-phrase title}

**ID:** `{DOMAIN.TOPIC.ACTION}`
**Trigger:** What initiates this (URL + verb, button label, webhook source, cron schedule).
**Actor:** Who acts (guest / staff role / owner / system / external service).
**Legacy locus:** File:line citations and stored-procedure names in the .NET codebase.

### Inputs (entities + datapoints)
Every field consumed. Names are the **legacy names** (`PropertyName`, `IsTwoFactoryAuth`, `EnquireSaurce`) including typos and inconsistencies — these are what the Django redesign will need to translate from.

### Process
Ordered steps. Cite stored procedures (`sp_villaEnquire`, `SP_SAVE_BOOKING_INFO`) and service methods (`ResService.PostEnquireNew`) by exact name.

### Outputs / side effects
- **DB writes:** table names + which columns change
- **State transitions:** any explicit status enum changes
- **Notifications:** emails sent (with template name), in-app toasts, log entries

### Third-party transmissions
External calls: endpoint URL pattern, auth scheme, request payload field names, response shape, retry policy.

### Data transformations for storage
How raw input becomes the stored row: hashing, currency conversion (e.g., GBP×100 cents), date parsing, JSON encoding, slug generation, enum mapping.

### Idempotency
**Required heading for every workflow whose trigger is a webhook, an integration push, a scheduler tick, or any retryable network call.** Other workflows may omit it.

State the dedupe strategy explicitly:
- What is the **idempotency key**? (provider event id, `(BookingId, EventType)`, request UUID, `(QuotationNo, ToDate)`, …)
- Where is it stored? (`WebhookDelivery.provider_event_id`, `SyncRecord.fingerprint`, …)
- What happens on a duplicate? (short-circuit and return prior result / no-op / error)
- Is the underlying operation **commutative** (last-write-wins is fine) or **non-commutative** (must dedupe)?

"It's idempotent" without naming the key or the storage is not a valid answer. Webhooks without dedupe are not idempotent; they are duplicable. The Django port should make this gap impossible to ship — `WebhookDelivery` and `SyncRecord` exist precisely so every integration declares its key.

### Failure modes
What can go wrong and how the legacy system reacts. Includes "silent failure" cases — they are not endorsements.

### Open questions / notes
Anything ambiguous, stubbed, disabled, or worth challenging during the Django implementation.
```

Some workflows are short enough that they fit in a few lines; others have all sections populated. The template is a checklist, not a quota.

## Conventions inside workflow text

- **Field names** are formatted as `FieldName` (inline code) and preserve the legacy casing/spelling.
- **Stored procedures** are formatted as `sp_villaEnquire` (inline code).
- **Status codes** — when the legacy system uses a magic integer (e.g., availability statuses 10/20/30/40/50/60/70), the file calls out the meaning the first time it appears and then references the number.
- **Bracket-tag for issues** the redesign should consider: `[STUB]` (referenced but not committed), `[DISABLED]` (commented out), `[SECURITY]` (issue worth flagging), `[CORRECTNESS]` (logical/atomicity defect in legacy code), `[TYPO]` (legacy misspelling preserved). These appear inline so they survive grepping.
- **Legacy spelling** is the source of truth in workflow specs (so the spec greps against the .NET source). The preserve-vs-rename decision for each typo lives in `../09-departures.md` → "Legacy typo registry". Do not silently use the cleaned-up spelling in a workflow spec — that hides a real cross-talk hazard (see `SecurityDepositDays{Defunded,Refunded}AfterDeparture`).

## Numbering rationale

The numbering of domains roughly follows the legacy schema's foundation-to-frontline order:

1. **Identity** — who can act
2. **Administration** — what the system knows about (lookups, taxonomies)
3. **Catalog** — properties, the things being sold
4. **Pricing** — the rules that price them
5. **Directory** — who owns/manages/agents-for/stays-at them
6. **Availability** — when they can be sold
7. **Enquiry** — incoming interest
8. **Quotation** — priced offer
9. **Booking** — confirmed deal
10. **Payment** — money in/out
11. **Integrations** — pushing all the above out
12. **Automation** — scheduled / background work that touches all the above

A reader walking the folders in order encounters dependencies more-or-less in build order.
