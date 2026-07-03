# Quotation Construction

Searching property options to build a quote, recalculating when inputs change, listing existing quotations.

## Search property options for quote

**ID:** `QUOTATION.BUILD.SEARCH_OPTIONS`
**Trigger:** Staff opens the quotation builder for an enquiry, enters dates / property filters / guest count.
**Actor:** Staff.
**Legacy locus:** `ResService.cs:1881-2008` (`GetQuotationData`); calls down into the pricing engine (`PRICING.ENGINE.COMPUTE_QUOTATION`).

### Inputs
- `QuotationArgs` (extends `EnquireDetails`): customer fields, plus
- Travel: `FromDate`, `ToDate`, `TotalWeeks`, `IsSpecificDate` (true for exact dates, false for "flexible weeks")
- Guests: `Guests`, `Adults`, `Children`
- Property criteria: `VillaId`, `Minbed`, `Maxbed`, `RegionIds`, `CountryId`, `FeatureIds`, `PreferenceId`
- `QuoteRefNo` (optional staff reference)
- `IsUnbrandedVilla` (use unbranded URLs in the rendered quote)
- `EnquiryNote`, `PreferencesNote`
- `ClientDetailsId`, `QuotationNo` (set when editing an existing quote)

### Process
Invokes `PRICING.ENGINE.COMPUTE_QUOTATION`. Summary:
1. `sp_getQuotationData` filters candidate villas.
2. For each candidate: `sp_getAvailability` + `sp_getQuotationPrices` + `RatesModel.Calculate()`.
3. Returns `List<QuotationPageModel>` with `QuotationPriceModel` per villa.

### Outputs / side effects
- **No DB writes** — builder is read-only until save.

### Failure modes
- See pricing-engine doc.

### Redesign note — paginated candidate fetch + "Load more"

The SPA builder splits the legacy single-pass into two calls and **pages** the
candidate set rather than fetching every match at once:

1. `GET /properties?status=active&…filters…&page=N` — one page (50) of candidate
   villas, name-ordered (stable via the `["name", "id"]` tiebreaker above). The
   DRF envelope's `next`/`count` drive the builder.
2. `POST /pricing:quote-bulk` — prices **only that page's** candidates.

The builder accumulates priced options across pages and exposes a **"Load more"**
button while `next != null`. Because availability is decided at pricing time,
*candidate* pagination ≠ *available-result* pagination: a page may add few or no
available villas (the rest fall into the "unavailable" collapsible). A count line
("N available · priced M of T matching villas") makes that legible. `lastCriteria`
(the criteria the visible results were priced under) is recorded only on a
successful search, so a failed re-search never pairs a stale price with newly
entered criteria.

The lenient "capacity not set" hint (see `02-properties.md` `PropertyCapacity`)
is computed once per fresh search (page 1 only), not per page.

---

## Recalculate on field change

**ID:** `QUOTATION.BUILD.RECALCULATE`
**Trigger:** Staff modifies `FromDate`, `ToDate`, `VillaId`, `Guests` on the builder.
**Actor:** Staff.

### Process
Re-runs `GetQuotationData` with new args. Same as above.

### Outputs / side effects
- Updated prices in-screen.

---

## List quotations

**ID:** `QUOTATION.LIST`
**Trigger:** Staff opens the Quotations page; applies filters.
**Actor:** Staff.
**Legacy locus:** SP `sp_getQuotationMasterDataById` (poorly named — appears to handle both list and by-id).

### Inputs
- Filter `PageEventArgs`: dates, agent, stage, search.

### Process
1. Execute the SP with filter params.
2. Returns paginated `List<VillaQuotationMaster>`.

### Outputs / side effects
- Read-only.

### Open questions
- Rename the SP in the redesign — confusing semantics.
