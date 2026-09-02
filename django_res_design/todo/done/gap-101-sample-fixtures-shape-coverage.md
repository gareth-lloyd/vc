> **✅ RESOLVED (2026-09-02)** — the shape axis is built. `zoho_send_sample`
> now drives a registry of ten named scenarios selected with `--scenarios`;
> `_build_graph` became `baseline` and a bare run is unchanged. All eleven
> shapes tabulated below are reachable: `repush`, `status_transitions`,
> `multi_option_quote`, `discounted`, `mixed_currency`, `sparse_financials`,
> `anonymised_person`, `agency_only_contact`, `villa_churn`, `out_of_order`.
> The scenario names replaced the prose test batches in CHECK-001/003/004/005.
>
> **Three deviations from this ticket, all deliberate:**
>
> 1. **Default is `baseline`, not all** (the ticket sketched "default all,
>    mirroring `--kinds`"). A bare run must not fire ~60 POSTs at Limitless'
>    live sample flows and flood the sandbox with records nobody asked to read.
>    `--scenarios all` is one flag away.
> 2. **"Baseline byte-identical for a fixed seed" was dropped** as an
>    acceptance criterion — it was never achievable: `core/factories.py` draws
>    a `uuid4` run token and `properties/factories.py` uses an unseeded
>    `Faker("en_GB")`, so names, slugs and addresses differ every run whatever
>    the seed. Replaced with a guarantee that holds: the existing
>    enum-coverage test passes unchanged against `baseline`. What the ticket
>    actually wanted — that nothing Limitless mapped *moves* — is enforced
>    instead by pinning every factory-iterator draw (`CurrencyFactory`,
>    `CountryFactory`) at every call site, and tested by running a shape
>    scenario BEFORE baseline and asserting baseline's villa is still GB/GBP.
> 3. **`discounted` shipped without waiting for BUG-020.** The scenario
>    *demonstrates* the bug — the quote carries the discounted figure and the
>    converted booking the gross one, side by side in the CRM — so its test is
>    pinned to the quote side and survives BUG-020's landing.
>
> **Spun off:** **BUG-021** — `Person.anonymize()` blanks every phone to `""`,
> so a person holding two numbers violates `unique_contact_phone` and cannot be
> erased at all. Found by building `anonymised_person`; the scenario keeps one
> phone to stay on the working path.
>
> **Still open, and unchanged by this:** **GAP-097**. The awkward inputs are now
> reachable; the outcomes are still invisible while any 2xx stamps `IN_SYNC`.
> "The sample passed" does not mean anything until both halves are in.

# GAP-101 — `zoho_send_sample` covers enum *values* but not payload *shapes*

- **Severity:** 🟠 Gap (the integration partner builds against this sample, so
  its blind spots become their bugs; it is also our only pre-flight check of
  the Zoho contract).
- **Source:** 2026-09-02, retrospective across the five Flow reviews
  (CHECK-001–005). Every significant finding was a shape the sample cannot
  produce.
- **Files touched:**
  - `django_res/seeding/management/commands/zoho_send_sample.py` — `_build_graph`
    (one graph, lines 278–556) and `add_arguments` (lines 97–107).
  - `django_res/seeding/tests/test_zoho_send_sample.py`.

## Problem

The command does exactly what its docstring promises: it constructs a synthetic
graph "deterministically populating at least one example of every attribute
that transmits a closed enum". That axis is the right one and should stay — it
is why `RoomFloor.LOWER_GROUND`, `BedSize.SUPER_KING` and the charge-only
`ChargeCategory.DAMAGE`/`CREDIT` values are on the wire at all.

But enum coverage is coverage of **values**, not of **shapes**, and the graph is
structurally the simplest instance of every entity:

- **one** quotation, with **one** line, **zero** discount, **one** currency;
- **one** booking, created from that line, never cancelled and never amended;
- every record pushed **exactly once**, in dependency order, first-create;
- a person who is never anonymised, a contact who always has a last name;
- a villa with rooms that are never deleted and a management company that is
  never replaced;
- financials that are always fully populated.

Sort the CHECK findings by whether the sample could have surfaced them and the
pattern is uncomfortable:

| Finding | Shape needed | In the sample? |
| --- | --- | --- |
| CHECK-004 item 1 / CHECK-005 item 3 — **insert-only**, every update silently discarded | any record pushed **twice** | no — one push per record |
| CHECK-004 item 2 / CHECK-005 item 4 — `Status` / `Quote_Stage` hardcoded | a **status transition** after the first push | no |
| CHECK-005 item 1 — multi-option lines summed as a basket | a quote with **N alternative lines** | no — always one |
| CHECK-005 item 2 / BUG-020 — discounted quotes overstated | a line with **`discount > 0`** | no — always zero |
| CHECK-005 — header currency taken from line 1 | lines in **two currencies** | no — one currency |
| CHECK-004 item 5 — sparse financials land at zero | a booking with **no schedule / null figures** | no — always populated |
| CHECK-004 item 6 — stub villa attaches the booking to the wrong villa | a booking arriving **before** its villa | no — strict dependency order |
| CHECK-004 item 7 — "Unknown" contact orphans | an **anonymised** person (`_person_summary` → `None`) | no |
| CHECK-001 item 2 — mandatory `Last_Name` rejection | an **agency-only** contact | no |
| CHECK-003 item 3 — subform re-creates rows; empty list omits the key | the **same villa pushed twice**, then a room deleted | no |
| CHECK-003 item 2 — an ended assignment beats the current one | a villa whose **management company was replaced** | no |

Eleven of the highest-blast-radius findings, none of them reachable. All were
found by reading Deluge by hand against the payload builders. That is not a
sustainable review method, and it is not one Limitless can run against
themselves.

The second-order problem is the false confidence. The command reports
`SyncRecord` outcomes, and the 2026-08 exercise "live-verified 5×IN_SYNC" — a
verification that, per **GAP-097**, means only that the Flow returned 200.
A wider fixture set makes the sample better at *originating* the awkward cases;
it does not make the result readable until GAP-097 lands. Both halves are
needed before "the sample passed" means anything.

## Proposed fix

Add a **shape axis** alongside the existing enum axis. The shapes conflict with
each other — a cancelled booking and an active one cannot be the same booking —
so this is several small scenario graphs, not one larger one.

- Refactor `_build_graph` into a registry of named scenarios, each returning a
  `SampleGraph`, all built and pushed inside the one existing
  `transaction.atomic()` / rollback envelope. Keep today's graph as the
  `baseline` scenario, unchanged, so the enum guarantee in the docstring still
  holds and nothing Limitless has already mapped moves.
- New `--scenarios` argument mirroring `--kinds` (comma-separated subset,
  default all), so a single awkward case can be pushed in isolation while
  someone watches the CRM.
- Scenarios to add, each named for the shape it exists to exercise and
  cross-referenced in a comment to the CHECK item it would have caught:
  `repush` (push, mutate a field, push again — the single most valuable one,
  since it is the only way insert-only semantics are observable),
  `status_transitions` (quote `accept`/`expire`/`cancel`; booking through to
  `cancelled`), `multi_option_quote` (N alternative lines, one `is_selected`),
  `discounted` (non-zero line discount), `mixed_currency`, `sparse_financials`,
  `anonymised_person`, `agency_only_contact`, `villa_churn` (re-push, delete a
  room, replace the management company), and `out_of_order` (booking before
  villa, to exercise the stub path deliberately rather than by accident).
- Because every generated record is already `_TAG`-prefixed and rolled back,
  the marginal cost of each scenario is small; the constraint is push volume
  against the sample webhooks, which `--scenarios` handles.

Worth deciding at the same time whether the scenario names become the shared
vocabulary with Limitless — "run `--scenarios repush,discounted` and read the
two records" is a far cheaper verification instruction than the prose test
batches CHECK-003 and CHECK-005 currently carry.

## Acceptance

- Each scenario builds, pushes and rolls back cleanly, with no residue beyond
  the known `PropertyImage` media path the command already reaps. (test)
- `--scenarios` selects a subset; an unknown name is a `CommandError`, not a
  silent skip. (test)
- The `baseline` scenario's payloads are byte-identical to today's for a fixed
  seed — the enum guarantee is not weakened by the refactor. (test)
- `--dry-run` prints every scenario's payloads, so the fixture set can be
  reviewed without a webhook URL. (test)
- Each scenario asserts the *shape* it exists for is actually present in the
  built payload (e.g. `discounted` fails if the line discount is zero) — a
  scenario that silently stops exercising its case is worse than no scenario.
  (test)
- The CHECK-003 / CHECK-004 / CHECK-005 test batches are restated as scenario
  names in those tickets.

## Dependencies

- **GAP-097** — until a Flow response means something, a scenario can originate
  the awkward case but not confirm the outcome. Pair them: this ticket makes
  the bad inputs reachable, GAP-097 makes the bad outputs visible.
- **BUG-020** — fix before shipping the `discounted` scenario, or the sample
  teaches Limitless the wrong contract by pushing the inflated figure our own
  conversion currently produces.
- **GAP-095** — an erasure scenario belongs here once the mechanism is chosen;
  `anonymised_person` is the read-side half of it.
- **GAP-096** — `out_of_order` exists to prove the stub-villa path; the ordering
  fix itself is GAP-096's.
- **CHECK-001 / CHECK-003 / CHECK-004 / CHECK-005** — the source of every shape
  listed above, and the consumers of the result.
