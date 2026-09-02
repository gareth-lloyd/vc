# CHECK-005 — Zoho quote flow: fixes raised with Limitless

- **Severity:** 🔎 Check (external party — closed by verifying someone
  else's change, not by building).
- **Owner of the work:** Limitless (Zoho Flow `limitless_insert_quote`).
  Not in this repo.
- **Raised:** 2026-09-02, by email, off the quote-sync demo transcript + the
  Deluge insert function.
- **Verify with:** `manage.py zoho_send_sample` against the Limitless
  sandbox, then read the resulting Quotes. Item 1 needs a **multi-line**
  quote and item 2 a **discounted** one — the synthetic sample is
  single-line with a zero discount, which is precisely why neither surfaced
  in their testing.

## Why this is a check, not a gap

Our payload (`build_quotation_payload`) carries everything below. Four items
are ours and are filed separately:

- **BUG-020** — the same `snapshot["total"]` mistake as item 2, in *our*
  conversion path. Confirmed by probe, not inferred.
- **FG-018** — the two-keys-named-`total` contract that caused both.
- **GAP-100** — we push a quote only at send, so status changes can never
  reach the CRM even with their half of item 3 fixed.
- **GAP-095** (erasure, item 9) and **GAP-096** (push ordering, item 10)
  as before.

## Items to verify

1. **Quote lines are alternatives; the subform treats them as a basket.** 🔴
   A quotation is multi-option by design — `one_selected_line_per_quotation`
   is a partial unique constraint, and `Quotation.accept()` is what sets
   `is_selected`. Lines are mutually exclusive: different weeks (GAP-043),
   occupancy bands (GAP-044), sometimes different villas. The Flow appends
   **every** line's villa row and extras into one `Quoted_Items` subform, so
   a three-option quote at £2,050 each reads as a £6,150 Zoho Quote. Related:
   `Villa_Name` is the first line's product and the header
   `No_of_Adults`/`No_of_Children`/`No_of_Nights` come from `line_index == 1`
   — and `ordering = ["pk"]` means "first built", not best or likeliest.
   - **This is a modelling question, not a patch.** Options put to them: one
     Zoho Quote per option; one Quote holding only the selected option; or
     alternatives marked as non-summing rows if the CRM supports it. We also
     offered to change the payload shape. **Settle this on a call before
     anything else here is worth verifying.**
   - *Verify:* a three-option quote — what is the grand total?

2. **Discounted quotes are overstated by exactly the discount.** 🔴
   `gross_price = snapshot.get("total")` falling back to `line.get("total")`
   — the fallback is the correct value. `pricing_snapshot["total"]` is the
   engine figure *before* the operator discount; `line.total` is
   `max(gross − line.discount, 0)`, the number the guest is quoted
   (`services/quotations.py:89`). `discount` is in the payload twice and read
   never. Asked for: read `line.total`.
   - *Verify:* a quote with a non-zero `discount`.
   - Ours: **BUG-020** (same error, our conversion path — the guest was
     quoted £1,250 and booked at £1,400) and **FG-018** (the contract that
     invites it). The email says both, and says we're fixing ours.

3. **Insert-only — and we only push once anyway.** 🔴 The Flow COQLs `Quotes`
   by `RES_ID` and returns early on a hit. Our side pushes only at send
   (`auto_push=False`, `quotation_transmission.py:216`). Between the two,
   `accepted` / `expired` / `cancelled` can reach the CRM by no route at all.
   Asked for: an update branch. **Our half is GAP-100 — coordinate; neither
   half alone changes anything observable.**
   - Consequence worth stating to them: `is_selected` is always `false` on
     the wire today, because it is set at `accept()` and we never push after
     send. It cannot be used to identify the winning option until GAP-100
     lands.

4. **`Quote_Stage` hardcoded to `"Quoted"`.** 🟠 We send five
   `QuotationStatus` values. Nearly harmless today because of item 3 — at
   push time the status genuinely is `sent` — but it hardcodes an assumption
   that breaks silently the moment either half of item 3 lands. The dev's
   stated reasoning ("as these statuses accepted on the inbound webhook")
   reads off the synthetic sample, where `status` happens to be `accepted`.
   - *Verify:* after GAP-100, an accepted quote reads as accepted.

5. **Header currency synthesised from line 1; quotes are legitimately
   mixed-currency.** 🟠 `build_quotation_payload` deliberately carries **no**
   header currency — GAP-014, per-line currency, mixed is expected and not
   normalised. The Flow takes `quote_currency` from the first line, puts it
   on the record, and gives each row its own `Currency_of_Quoted_Item`.
   Combined with item 1, Zoho sums rows across currencies under one record
   currency — silently, and wrong by an arbitrary amount.
   - *Verify:* a quote with lines in GBP and EUR.

6. **Net recomputed, tax dropped — and the right figure is in the
   payload.** 🟠 `net_price = gross_price − snapshot.commission`; ours is
   `total − commission − tax`, so they disagree on anything carrying local
   VAT (GAP-079). Unlike the booking flow, the fix here is trivial:
   `pricing_snapshot.net_to_owner` is already in the payload. Also unread:
   `commission_base`, `extras_non_commissionable_total`, and the per-extra
   `commissionable` flags — the GAP-076 pass-through story they'd need to get
   commission right by hand.
   - *Verify:* a quote on a property with non-zero tax.

7. **`expires_at` is dropped.** 🟠 `Valid_Until` is a standard Zoho Quotes
   field, it was on the legacy `QuotationPostData` checklist, and quote
   expiry is the one date on a quote anyone chases.

8. **`enquiry`, `agent`, `is_unbranded`, `terms_version`, `cancel_reason`
   dropped.** 🟠 With CHECK-004 item 8 this breaks enquiry → quote → booking
   at **both** hops. `is_unbranded` marks a white-labelled agent quote — a
   commercial distinction worth a checkbox.

9. **Contact creation is the fourth copy, third mapping.** 🟠 Byte-identical
   to the booking Flow's block: `primary_phone` → `Mobile` unconditionally
   (five `PhoneLabel` values; primary is often a landline), and the
   `"Unknown"` fallback that fires exactly when `person` is null — which is
   what an erased Person looks like, since `_person_summary` fails closed.
   One unmatchable orphan per erased-person quote. Asked for: skip the create
   when there is no `RES_ID`, and share one routine across all four flows.
   - Cross-ref **GAP-095**; symptom, not fix.

10. **Stub-villa block is a second copy, same wrong-villa attach.** 🟠 Same
    ~150 lines as the booking Flow, same final branch logging
    `"this quote line will attach to the wrong villa"` before doing it.
    Asked for: abort. Widens the ordering problem — quotes can now mint stub
    Products too (**GAP-096**).
    - Credit where due: the `product_cache` keyed on `property_res` means a
      multi-option quote on one villa resolves it once. Keep that.

## Open decision — extras

Same as CHECK-004: one hardcoded `extras_product_id` for every extra, with
label and type concatenated into `Description`, so per-type reporting is
impossible. **Whatever is settled on CHECK-004 applies here identically —
do not decide these separately.**

One inconsistency to fix alongside it: this Flow reads `extra.kind`, the
booking Flow reads `extra.category`. Both are the GAP-088 vocabulary
(`ExtraKind` ⊂ `ChargeCategory`), but the same extra will render differently
depending on which record you are looking at.

## Smaller items

- **Line notes appear twice in the description.** `desc_lines.add("Notes: …")`
  and then `line_desc = line_desc + " | " + notes` after the join. Leftover;
  cosmetic but visible on the quote.
- **`RES_JSON` size risk, specific to quotes.** `pricing_snapshot.lines` is a
  **per-night** array. The 7-night sample is ~1KB of nightly rows; a
  three-option four-week quote is 80+ entries and could approach Zoho's
  32,000-char multi-line text limit. Asked: does Zoho truncate or reject?
  A rejected write would be recorded by us as `IN_SYNC` (**GAP-097**).
- **`RES_JSON` PII** — guest name, email, phone, in a field no erasure
  request reaches. Same as CHECK-003 / CHECK-004. **GAP-095**.
- **`Quote_Stage` aside:** section 3 is commented "QUOTE - upsert on RES_ID"
  but performs a plain POST. Worth flagging so the comment doesn't outlive
  the fix in item 3.

## How to originate these shapes (GAP-101)

Each quote shape below is now a named `zoho_send_sample` scenario — built
synthetically, pushed through the production pipeline, rolled back. Add
`--dry-run` to read the payloads without POSTing.

| Item | Command |
| --- | --- |
| 1 — multi-option lines summed as a basket | `--scenarios multi_option_quote` (three lines across two villas, one selected) |
| 2 — discounted quotes overstated | `--scenarios discounted` (a real `discount > 0`, netted off the line total) |
| 3 — insert-only, updates discarded | `--scenarios repush` |
| 4 — `Quote_Stage` hardcoded "Quoted" | `--scenarios status_transitions` (SENT → ACCEPTED, and a second quote SENT → CANCELLED) |
| 5 — header currency taken from line 1 | `--scenarios mixed_currency` (GBP and EUR lines in one quote) |

`discounted` also pushes the booking converted from that line. Until
**BUG-020** lands, the two records disagree in the CRM by design — the quote
carries the discounted figure and the booking the gross one. That divergence is
the demonstration; do not treat the booking figure as the contract.

Caveat unchanged: per **GAP-097** the run's own `IN_SYNC` means only that the
Flow answered 2xx. "Verified" still means a human opened the CRM record.

## Related

- **BUG-020** · **FG-018** · **GAP-100** — the ours-side split from this
  review.
- **GAP-095** erasure · **GAP-096** push ordering · **GAP-097** delivery
  confirmation.
- **CHECK-001** contacts · **CHECK-002** enquiries · **CHECK-003** villas ·
  **CHECK-004** bookings.
