# Q-013 — Rate-card "incomplete pricing" behaviour

- **Severity:** Question
- **Source:** `product-design/06-verification.md` open question 13
- **Blocks:** Quotation builder UX, pricing engine fallbacks
- **Status:** ✅ Resolved 2026-06 — option 1 (flag + manual quote), per legacy.

## Question

Flow 2 step 4 references "if villa's rate card incomplete for some
nights, card flags 'Incomplete pricing — manual quote'". Confirm:

- Acceptable as-is — operator can type a price for missing nights, the
  villa stays selectable.
- OR hide the villa entirely from quotation results when pricing is
  incomplete.

The first option is the design's current direction; the second is
simpler but loses revenue.

## Answer

**Option 1 — flag + manual quote. The villa is never hidden.** Legacy
evidence settled it (follow-legacy-for-customer-facing rule):

- `RateLookup.razor:400–409` renders the literal **"NO RATE"** in the
  price cell when no price resolves, but the week's selection checkbox
  (`:413–417`) is gated only on `IsBook` — NO RATE rows stay selectable.
- `Booking.razor:122` binds `RentalPrice` to an editable input; the
  operator types the price, the screen never auto-computes it.
- `RatesModel.cs:116–123` zeroes POA rates into the same NO RATE path.
- `QuoteGenerator.razor:833/887` unions operator-added villas onto
  quotes with `IsManual = true` — fully manual villas are first-class.

## What was built (2026-06)

- **Backend:** `PricingQuoteBulkView` already returned
  `error_code="no_rate_available"` for unpriceable entries; the error
  branch now also carries `hero_image_url` and the property's resolved
  `currency_code` (via `resolve_property_currency`) so the manual card
  renders like its priced siblings and the operator sees the currency
  the manual total will save in. No engine change — `incomplete=True`
  markers were not needed; the existing exception code is the marker.
- **Frontend builder:** `QuoteResultsList` splits three ways —
  available / manual-quotable (`error_code === "no_rate_available"`,
  flagged "Incomplete pricing — manual quote" in the main list with an
  "Add manually" button) / other errors (still collapsed, unselectable).
  "Add manually" stages the line `is_manual` from the start
  (`manual_only` pins the checkbox), the cart auto-expands the new line
  onto its total/reason inputs once, and the existing staged-line
  validation (total > 0 + non-blank reason) gates Save.

## Accepted behaviours (not bugs)

- **POA villas share the `no_rate_available` flag.** Legacy parity: POA
  renders as NO RATE there too. The card's tooltip surfaces the engine's
  `error_detail`, which is what distinguishes a rate-card gap from a
  deliberate POA rule.
- **Manual lines bypass the changeover auto-shift.** The operator's
  typed dates and price are taken as-is (operator judgement, matches
  legacy manual bookings).
