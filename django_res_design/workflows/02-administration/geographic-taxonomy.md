# Geographic Taxonomy

Countries are the root of the geographic hierarchy; regions hang off countries. Both are pushed to the public WordPress site.

## Manage country (CRUD + reorder)

**ID:** `ADMIN.GEO.COUNTRY_UPSERT`, `ADMIN.GEO.COUNTRY_DELETE`, `ADMIN.GEO.COUNTRY_REORDER`
**Trigger:** Admin actions on `/countries` (`NewResSystem/Pages/Admin/Country.razor`).
**Actor:** Admin (`Authorize(Roles="Admin")`).
**Legacy locus:** `Country.razor`, `ResService.cs:46` (CRUD), `ResService.cs:294-307` (reorder loop).

### Inputs
- `Id` (0 for INSERT)
- `Name` (required, unique)
- `ShortName1` (ISO 3166-1 alpha-2)
- `ShortName2` (ISO 3166-1 alpha-3)
- `Code` (numeric ISO code, int)
- `TaxRate` (decimal, VAT % default for the country)
- `IsActive` (bool)
- `Order` (int; managed via drag-drop)
- `User` (admin username)
- `Action` (`INSERT`/`UPDATE`/`DELETE`/`ORDER`)

### Process
1. Uniqueness pre-check for INSERT/UPDATE: `SP_COUNTRIES` with `@Action=SELECTEXITS`. If a non-deleted row matches `Name`, return `"Country {Name} is already exist in the res system!"`.
2. Main call: `SP_COUNTRIES` with the supplied action. Output param `@CountryId` returns the row id.
3. For reorder: iterate the reordered UI list, sending one `SP_COUNTRIES @Action=ORDER` per row with the new `Order` value (`Country.razor:294-307`).
4. If `AllowSyncOnUpdate() > 0` and the action isn't local-only: `UpdateSyncId(ResModule.COUNTRY, countryId, 0, userId, DbAction.UPDATE)` then `_apiService.CountrySync(SyncPostData { ApiAction, Id, LoggedUser })`.

### Outputs / side effects
- **DB write:** `VillaCountry` (INSERT/UPDATE/soft DELETE) with `CreatedAt`/`CreateBy`/`UpdatedAt`/`UpdatedBy`/`DeletedAt`/`DeletedBy`/`SyncId=0` (marked for push).
- **Sync queue:** A pending sync row keyed `(VillaCountry, id, COUNTRY)`.
- **Outbound push:** see `INTEGRATIONS.PUBLIC_API.COUNTRY_SYNC` in `11-integrations/public-website-sync.md`.

### Data transformations for storage
- `Order` is rewritten for **every** row in the list on a single drag — N calls per reorder, N round-trips. Should be a single bulk write in Django.

### Failure modes
- Duplicate name → blocked.
- Soft-deleted row with same name → SP returns "exist"; admin must restore via the row trash flow rather than re-create.
- Sync failure post-DB-commit → logged silently; local row diverges from WordPress until the next sync run picks it up.

### Open questions
- `TaxRate` here is **the country default**; the per-property `VillaFinance.TaxPercentage` overrides via the `IsDefaultTax` flag. Django redesign should make the resolution explicit (`effective_tax_rate()` on the property).

---

## Manage region (CRUD)

**ID:** `ADMIN.GEO.REGION_UPSERT`, `ADMIN.GEO.REGION_DELETE`
**Trigger:** Admin actions on `/regions/{countryId}/{countryname}` (`NewResSystem/Pages/Others/Region.razor`).
**Actor:** Admin.
**Legacy locus:** `Region.razor`, `ResService.cs` (region CRUD path).

### Inputs
- `Id` (0 for INSERT)
- `CountryId` (route parameter)
- `Name` (required, unique-within-country)
- `Slug` (URL-friendly, generated from `Name`)

### Process
1. Uniqueness pre-check (within country): error `"Region {Name} is already exist in the res system!"`.
2. `SP_REGIONS` with `@Action` and supplied parameters. Output `@RegionId`.
3. Queue sync: `UpdateSyncId(20, regionId, 0, userId, UPDATE)` (note: numeric literal `20`, not a constant) → `_apiService.RegionSync(SyncPostData)`.

### Outputs / side effects
- **DB write:** `Regions` table.
- **Outbound push:** see `INTEGRATIONS.PUBLIC_API.REGION_SYNC`.

### Data transformations for storage
- Slug generation pattern not visible in the captured code — lowercase + hyphenation is the assumed convention. The redesign should use Django's `slugify`.

### Failure modes
- Duplicate region in same country → blocked.
- `CountryId` invalid → FK violation in SP.

### Open questions
- No "reorder" workflow for regions despite the same admin pattern as countries. Decide whether the redesign needs ordering for regions.
- Numeric module id `20` in code should be a named constant.
