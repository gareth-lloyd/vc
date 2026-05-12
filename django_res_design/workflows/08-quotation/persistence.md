# Quotation Persistence

Saving the quote header and the line items, applying discount and commission overrides.

## Save quotation master (header)

**ID:** `QUOTATION.PERSIST.SAVE_MASTER`
**Trigger:** Save on the quotation builder.
**Actor:** Staff.
**Legacy locus:** `ResService.cs:3985-4092` (`ResQuotation`); SP `sp_quotation_master`.

### Inputs
`VillaQuotationMaster` — ~40 fields:

Client (flattened from `EnquireDetails`):
- `ClientDetails.FirstName`, `LastName`, `Email`, `Title`, `CountryCode`, `MobileNo`, `Town`, `Country`, `PostCode`, `AddressLine1`, `AddressLine2`

Agent (`AgentDetails`):
- `AgentDetails.FirstName`, `LastName`, `Company`, `Email`, `CountryIds`, `RegionIds`, …

Quote header:
- `Id` (0 for new)
- `EnquireId` (link to parent)
- `QuotationNo` (auto-assigned by SP)
- `TotalWeeks`
- `Stage` = `ZohoQuoteStage.Draft`
- `Owner` (Zoho owner email; default `"info@villacollective.com"`)
- `ClientNotes`
- `PreferenceId` (multi-select Zoho tags)
- `FeatureId` (comma-string)
- `UnbrandedLinks` (bool)
- `ZohoVilla`, `ZohoCountry`, `ZohoRegion` (Zoho ref ids for cross-system lookup)

Line items:
- `QuotationDetails`: `List<QuotationDetailsArgs>` (see next workflow)

- `Action` ∈ {`INSERT`, `UPDATE_ENQUIRE`}

### Process
1. Build ~40 SP parameters (`ResService.cs:3991-4035`).
2. Execute `sp_quotation_master @Action=INSERT` (or `UPDATE_ENQUIRE`).
3. Output: `@QuotationId`, `@QuotationNo`, `@Enquire` (the parent enquiry id, possibly mutated).
4. If `Action == UPDATE_ENQUIRE`: build a `PostEnquireArgs` from the quote details (`ResService.cs:4047-4068`) and call `_apiService.PushZohoEnqueireAsync(postData)` to update the **enquiry** record in Zoho with the quote-derived data. This is the enquiry-write-through; the quote itself isn't yet in Zoho.

### Outputs / side effects
- **DB write:** `VillaQuotationMaster` (UPSERT) + flattened client/agent fields.
- **Zoho push (enquiry only):** updates the parent enquiry record. Quote → Zoho happens later on email send.

### Data transformations for storage
- `Guests = Adults + Children` computed.
- `No_of_Nights = (ToDate - FromDate).TotalDays`.
- `Valid_Until = ToDate.AddDays(6)`.

### Failure modes
- SP fails (duplicate quote number, FK violation) → exception; no commit.
- Invalid agent id → SP may accept NULL or default to system owner.

### Open questions
- Storing client/agent denormalised on the quote master means changes to a contact don't propagate to old quotes — sometimes desired ("historical snapshot"), sometimes a bug. The Django redesign should pick deliberately: either snapshot or FK with `protected_at` timestamp.

---

## Save quotation line items

**ID:** `QUOTATION.PERSIST.SAVE_LINES`
**Trigger:** As part of quotation save (after master), or when adding/removing villas.
**Actor:** Staff.
**Legacy locus:** `ResService.cs:3111-3169` (`SaveQuotationDetails`); SP `sp_saveQuotationDetails`.

### Inputs
- `List<QuotationDetailsArgs>` with `QuotationMasterId`, `VillaId`, `ZohoVilla`, `IsManual`, and a nested `Details` list:
  - `FromDate`, `ToDate`, `GrossPrice`, `CurrencyId`, `Currency`, `CurrencySymbol`, `Price` (formatted), `Inclusion`, `IsBook`, `IsHold`

### Process
1. For each villa:
   - Validate villa exists and rates configured.
   - Execute `sp_saveQuotationDetails` (one or more INSERT/UPDATE for each date range).

### Outputs / side effects
- **DB write:** `VillaQuotationDetail` rows.
- `IsManual=true` rows are preserved on recompute (the engine won't overwrite).

### Failure modes
- Overlapping date ranges for the same villa — no explicit check, may produce duplicate detail rows.
- Price with no rate definition + `IsManual=false` → falls back to property base or 0.

### Open questions
- Add explicit overlap prevention on lines for the same villa.

---

## Apply discount

**ID:** `QUOTATION.PERSIST.APPLY_DISCOUNT`
**Trigger:** Staff enters discount on the quote summary panel.
**Actor:** Staff.
**Legacy locus:** Discount field on `LineItem` flows through `QuotationBookingPostData.cs:143`.

### Inputs
- Discount amount (decimal) or percentage
- Scope: entire quote or specific villa line

### Process
1. Apply at the line-item level (`LineItem.Discount`).
2. Recompute: `Net = Gross - Discount`.
3. Tax = `Net × TaxPercentage` (if applicable; tax applied to net).
4. Total = `Net + Tax`.

### Outputs / side effects
- **DB write:** `VillaQuotationDetail.Price` (or a summary field) updated.
- **Zoho:** discount carried in `LineItem.Discount` when pushed.

### Failure modes
- Discount > Gross → negative price. Not validated.

### Open questions
- Decide cap: discount can't exceed gross.

---

## Set commission and agent split

**ID:** `QUOTATION.PERSIST.SET_COMMISSION`
**Trigger:** Staff assigns agent, selects commission type / amount, optionally splits VC/agent share.
**Actor:** Staff.
**Legacy locus:** Computed at quote save; flows into Zoho payload.

### Inputs
- `AgentDetails.Id`
- `CommissionType` (% or fixed), `CommissionAmount`
- `VC_Commission` (% of commission payable to VC vs agent/broker)

### Process
1. Inherit `CommissionType`/`CommissionAmount` from `VillaFinance` unless overridden.
2. Compute `Commission`:
   - `% type`: `Commission = Gross × CommissionAmount / 100`
   - `Fixed`: `Commission = CommissionAmount`
3. `VC cut = Commission × VC_Commission / 100`.
4. `Agent split = Commission - VC cut`.

### Outputs / side effects
- **DB write:** commission fields stored on quote/booking (exact column depends on finance summary).
- **Zoho payload (later):** `Commission_Total`, `VC_Commission`, `Agent_Split_Amount`.

### Failure modes
- Commission misconfigured → defaults to fixed-zero (silently free agency).

### Open questions
- Move commission math into a dedicated value object / service in the Django redesign — currently scattered.
