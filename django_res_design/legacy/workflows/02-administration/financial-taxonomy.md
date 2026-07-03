# Financial Taxonomy

Currencies are the only system-wide financial reference data. FX rates are **not** managed here — there is no FX-rate workflow in the legacy code; per-property pricing carries its own currency, and Flywire performs settlement conversion at payment time.

## Manage currency (CRUD + reorder + set-default)

**ID:** `ADMIN.FINANCE.CURRENCY_UPSERT`, `ADMIN.FINANCE.CURRENCY_DELETE`, `ADMIN.FINANCE.CURRENCY_REORDER`, `ADMIN.FINANCE.CURRENCY_SET_DEFAULT`
**Trigger:** Admin actions on `/currencies` (`NewResSystem/Pages/Admin/Currencies.razor`).
**Actor:** Admin (`Authorize(Roles="Admin")`).
**Legacy locus:** `Currencies.razor`, service goes through `sp_currencies`.

### Inputs
- `Id` (0 for INSERT)
- `Name` (e.g., "US Dollar")
- `CurrencyCode` (e.g., "USD", expected to be ISO 4217)
- `Symbol` (e.g., "$")
- `IsShowAfter` (bool — whether the symbol renders after the amount, `"100 €"` vs `"$ 100"`)
- `IsDefault` (bool — only one currency may carry this)
- `Order` (int)
- `Action`

### Process
1. `sp_currencies` with the supplied action.
2. **No uniqueness pre-check on `CurrencyCode`** in the captured code — name uniqueness is enforced (pattern from other admin entities) but currency code uniqueness is implicit.
3. Reorder: same N-call loop pattern as countries (`Currencies.razor:209-220`).
4. Set-default: send `IsDefault=true` for the chosen row. The SP is expected (but not verified in committed code) to clear `IsDefault` on all others.

### Outputs / side effects
- **DB write:** `VillaCurrency` row, audit fields populated.
- **No sync to WordPress.** Currencies remain local; the public site uses its own currency configuration. Property pricing references `CurrencyId` and the symbol is sent in line items.

### Data transformations for storage
- All fields as-is. Amount precision (per currency) is **not** modelled; everything uses `decimal` and assumes 2 fractional digits implicitly. `[STORAGE]` issue — JPY/KRW have 0, BHD has 3. The Django redesign should carry `fractional_digits` per currency.

### Failure modes
- Currency in active use: a delete will succeed at the SP level but will leave dangling FKs in `VillaSeasonRate`, `VillaPayment`, etc. — soft-delete means those rows still join. Test before deleting.
- Multiple `IsDefault=true` rows: not constrained in code; relies on SP discipline.

### Open questions
- The redesign should model currency precision (`fractional_digits`), add a uniqueness constraint on `code`, and use `EXCLUDE`-style enforcement of single-default (or a partial unique index `WHERE is_default`).
