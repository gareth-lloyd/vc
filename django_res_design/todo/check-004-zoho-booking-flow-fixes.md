# CHECK-004 — Zoho booking flow: fixes raised with Limitless

- **Severity:** 🔎 Check (external party — closed by verifying someone
  else's change, not by building).
- **Owner of the work:** Limitless (Zoho Flow `limitless_insert_booking`).
  Not in this repo.
- **Raised:** 2026-09-02, by email, off the booking-sync demo transcript +
  the Deluge insert function.
- **Verify with:** `manage.py zoho_send_sample` against the Limitless
  sandbox, then read the resulting Sales Orders. Item 1 needs a **second**
  push of the same booking after a status change — one push proves nothing.

## Why this is a check, not a gap

Our payload (`django_res/reservations/services/zoho_payload.py`,
`build_booking_payload`) already carries everything below, including the
GAP-085 `financials` block and the GAP-088 `extras[]` taxonomy. Three items
from this review are ours and are excluded here:

- explicit deposit/balance **payment status** in the financials block →
  **GAP-099** (raised in the email as an offer, not a request);
- villa-before-booking **push ordering** so the stub path is rarely taken →
  the backfill-ordering section of **GAP-096**;
- the erasure and PII-snapshot angles (items 7 and 10b below touch them) →
  **GAP-095**. Do not close GAP-095 by closing this ticket.

Item 1 is also the sharpest illustration to date of **GAP-097**: we stamp
`IN_SYNC` on the 2xx the Flow returns *immediately before discarding the
update*. Until GAP-097 lands, `SyncRecord` cannot be used as evidence that
any item here is fixed — hence the two-push verification above.

## Items to verify

1. **Insert-only, but we push on every update.** 🔴 The headline.
   `register_zoho_flow(Booking, kind="booking", …)`
   (`reservations/apps.py:274`) takes the default `auto_push=True` and sets
   no `ignore_update_fields`, so every `Booking.save()` pushes. The function
   COQLs `Sales_Orders` for the `RES_ID` and returns early on a hit, so the
   CRM holds each booking at its *earliest* state forever. Discarded:
   the whole `BookingStatus` walk, cancellation (+ `cancel_reason`,
   `cancelled_at`), `modify_dates` / `modify_guests`, payments landing,
   charge items, the GAP-087 deposit override, `is_archived`. Asked for: an
   update branch, same shape as the villa flow's `Products` PUT.
   - *Verify:* push a booking, change its status, push again, and read the
     record. Nothing below is meaningfully verifiable until this passes.

2. **`Status` is hardcoded to `"Pending Booking"`.** 🔴 We send 11
   `BookingStatus` values (`reservations/enums.py:94`). With item 1 this
   means the CRM believes every booking — cancelled ones included — is
   pending in perpetuity. We offered to supply the full 11-value mapping
   once they send the `Sales_Orders` status picklist.
   - *Verify:* a cancelled booking reads as cancelled.

3. **`Deposit_Received` is a negative test.** 🟠
   `status != "awaiting_deposit"` → true, which marks the deposit received
   on `draft`, `pending_owner_approval`, `cancelled`, `expired` and
   `declined`. Asked for: a positive membership test over `deposit_paid`,
   `awaiting_balance`, `balance_paid`, `checked_in`, `checked_out`.
   Superseded if they take up GAP-099.
   - *Verify:* a draft booking and a cancelled booking both read as
     deposit-not-received.

4. **The subform recomputes net and disagrees with our authority.** 🟠
   `net_price = gross_price - snapshot.commission`, where `snapshot` is
   `payload.line.pricing_snapshot`. Three faults compounding:
   - **Wrong snapshot.** That is the *quote line*'s snapshot;
     `owner_money_for_booking` reads `booking.pricing_snapshot`
     (`reservations/services/owner_finance.py:86`), which is deliberately
     not in the payload. They diverge after any reprice or date/guest
     modification.
   - **Tax dropped.** `owner_finance.py:63` is
     `net = total − commission − tax`; theirs omits tax, so `Net_Price` ≠
     `Total_Net_Amount` on every booking carrying local VAT (GAP-079).
   - **It is the derivation GAP-085 exists to prevent.** Commission is not
     proportional — GAP-076 pass-through extras carry none, GAP-077 puts the
     residual on BALANCE, and `charges_owner_adjustments` applies a
     `commission_delta` that never touches the snapshot.

   Asked for: don't derive net in the subform. Let `Booking_Total` /
   `Total_Net_Amount` (straight from `financials`) be the only net figures,
   and set the villa row's `Net_Price` to its gross or leave it unset. A
   genuine per-row net would be an **[us]** payload extension — offered, not
   promised; file a gap if they take it up.
   - *Verify:* a booking with non-zero tax — subform net vs
     `Total_Net_Amount`.

5. **Sparse-financials bookings land silently at zero.** 🟠 `financials`
   keys are nullable by design (`_financials_payload` returns
   `dict.fromkeys(...)` when `owner_money_for_booking` is None — never
   invented zeros). The fallback to `snapshot.total` is also empty on those
   rows, so the villa row prices at `0.0`, `Booking_Total` is never set, and
   the record is created with no money and no warning. This is the *expected*
   shape for the spreadsheet-imported historic bookings (see the 2026-07-29
   Limitless call — import pivot). Asked for: log/flag rather than write a
   zero.
   - *Verify:* push a booking whose `pricing_snapshot` lacks
     `total`/`commission`/`tax`.

6. **The villa-stub duplicate branch attaches bookings to the wrong
   villa.** 🟠 The `DUPLICATE_DATA` path adopts the colliding Product; when
   its `RES_ID` is non-empty and different, the function logs
   `"…this booking will attach to the wrong villa."` and then does exactly
   that. Asked for: abort. A booking that fails to create is recoverable; one
   silently bound to the wrong villa is not. (Relevant precedent: legacy
   `VillaMaster` 88 and 339 are distinct villas sharing one ZohoId —
   `data_migration/loaders/integrations.py:105`.)
   - *Verify:* two Products with the same `Product_Name` and different
     `RES_ID`s.

7. **A third writer to Contacts, with a third field mapping.** 🟠 The
   contact, enquiry and booking flows each create Contacts differently. Here
   `primary_phone` → `Mobile` unconditionally, though `PhoneLabel` has five
   values and the primary phone is frequently a landline. Worse: when
   `person` is `null` — which is exactly what an erased Person looks like,
   `_person_summary` fails closed — `person_res` is `""`, the search is
   skipped and the flow creates a contact named **"Unknown"** with no
   `RES_ID`. One unmatchable orphan per erased-person booking. Asked for:
   skip the create entirely when there is no `RES_ID`, and share one
   contact-create routine across the three flows.
   - *Verify:* push a booking whose person is `PersonStatus.ANONYMIZED`.
   - Cross-ref **GAP-095**; this is the CRM-side symptom, not the fix.

8. **`agent`, `assigned_to` and `enquiry` are all dropped.** 🟠 Same gap as
   the enquiry flow (CHECK-002 item 3), now on bookings too: agency
   attribution is invisible, and the Sales Order is not linked to its Deal,
   breaking the enquiry → quote → booking chain at the last hop.
   - *Verify:* an agency booking — is the agent anywhere on the record?

## Open decision — extras reporting

Every extras row points at one hardcoded `extras_product_id`, with the label
and the GAP-088 `category` concatenated into `Description` free text. That
makes per-category reporting ("cleaning / transfers / cots, last year")
impossible. We built the `ChargeCategory` taxonomy specifically to give them
a stable vocabulary. Asked in the email: a Product per category, or a
picklist field on the subform row? Either is fine on our side — the payload
does not change. **Decide before closing this ticket.**

## Smaller items

- **Datetimes carry no offset.** `Arrival_Date` / `Departure_Date` are
  written as `"…T12:00:00"`, which Zoho reads in the org timezone and can
  display a day out elsewhere. Asked for: an explicit offset, or plain date
  fields. (Our `date_from`/`date_to` are dates, so `subString(0,10)` is a
  no-op — harmless.)
- **`RES_JSON` holds the full payload, PII included** — guest name, email,
  phone, line inclusions and notes, in a text field no erasure request can
  reach. Same finding as the villa flow's `RES_Source_JSON`
  (CHECK-003). Also: `payload.toString()` is Deluge map stringification,
  not guaranteed-valid JSON. Cross-ref **GAP-095**.
- **`site_source` and `payment_method` are unmapped.**
- **`quote.is_synthetic` is ignored.** Legacy-imported bookings carry a
  booking-synthesised quotation that deliberately never pushes as the quote
  kind, so the `Quotes` COQL will always miss. The flag would let them tell
  "no quote expected" from "quote missing".
- **Multi-currency assumption.** `Currency` on the record and
  `Currency_of_Booked_Item` on rows both require multi-currency enabled in
  the org with our booking currency's code present. Worth confirming rather
  than assuming.
- **Create/update race.** A rapid create-then-update, or our retry/sweep
  re-firing, could race the COQL existence check into two Sales Orders. The
  item-1 fix should make the write idempotent on `RES_ID` rather than
  guarded by a prior read.

## Related

- **GAP-095** erasure propagation · **GAP-096** Organisation push kind (+
  backfill ordering) · **GAP-097** delivery confirmation · **GAP-099**
  explicit payment status.
- **CHECK-001** contacts · **CHECK-002** enquiries · **CHECK-003** villas.
