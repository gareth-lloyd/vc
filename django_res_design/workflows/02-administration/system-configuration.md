# System Configuration

Four independent configuration sections, each on its own tab in `/config` (`Pages/Admin/Configuration.razor`). All require `Authorize(Roles="Admin")`. Each tab posts to its own stored procedure.

## Save general configuration

**ID:** `ADMIN.SYSCONFIG.GENERAL_SAVE`
**Trigger:** Save button on the General tab (`Configuration.razor:552`).
**Actor:** Admin.
**Legacy locus:** `ConfigurationService.SaveVillaConfigGeneral`, SP `SP_CRUD_VILLACONFIGGENERAL`.

### Inputs
- `name` (system instance name)
- `url` (system base URL — used to construct callback/return links in templates)
- `apikey` (system-wide API key used for callbacks from external systems, e.g., the scheduler trigger)

### Process
1. `SP_CRUD_VILLACONFIGGENERAL` with `@Action=INSERT` (UPDATE path commented in the form).

### Outputs / side effects
- **DB write:** `VillaConfigGeneral`.
- **No cache invalidation**: the rest of the system loads this on demand.

### Open questions
- `apikey` is the same value as the hardcoded key in `PaymentController` (`130d0022-…`) — see `10-payment/checkout-flow.md`. Redesign should pull from environment-managed secret storage.

---

## Save website (multi-tenant target) record

**ID:** `ADMIN.SYSCONFIG.WEBSITE_UPSERT`, `ADMIN.SYSCONFIG.WEBSITE_DELETE`
**Trigger:** Save / trash actions on the Website tab.
**Actor:** Admin.
**Legacy locus:** `Configuration.razor:629-635`, SP `sp_sites_register`.

### Inputs
- `Name` (display name)
- `url` (required) — the WordPress site base URL
- `IsSyncApi` (bool, **hardcoded `true`** in form `Configuration.razor:628`)
- `apikey` (bearer token for the WordPress REST API; **hardcoded UUID** in form `Configuration.razor:625`)

### Process
1. `sp_sites_register` with the supplied action.

### Outputs / side effects
- **DB write:** `VillaConfigWebsite`.
- This table is consumed by every `*Sync` workflow in `11-integrations/public-website-sync.md` — each row represents one WordPress site that receives mirrored data.

### Open questions
- Multi-tenant is real (the sync code groups by `SiteId`). Confirm whether VC2 actually runs to multiple sites — if not, simplify.
- The `apikey` UI literal is an unencrypted bearer token at rest. Move to encrypted storage in the redesign.

---

## Save email configuration

**ID:** `ADMIN.SYSCONFIG.EMAIL_SAVE`
**Trigger:** Save button on the Email tab.
**Actor:** Admin.
**Legacy locus:** `Configuration.razor:681`, SP `SP_CRUD_VillaConfigEmail`.

### Inputs
Sender:
- `fromname` (display name)
- `fromaddress` (reply-to)
- `errortogeneric` (catch-all error destination)

SMTP server:
- `serveraddress`, `serverport`
- `servertls` (bool), `serverauthentication` (bool)
- `serverusername`, `serverpassword`

### Process
1. `SP_CRUD_VillaConfigEmail`.

### Outputs / side effects
- **DB write:** `VillaConfigEmail` row.
- This is the fallback SMTP profile when a user has no per-user SMTP set. Per-user SMTP is in `UserMaster` (see `01-identity/user-administration.md`).
- **No live verification of the SMTP credentials** — the admin learns the next time someone sends an email.

### Open questions
- `serverpassword` is stored plaintext `[SECURITY]`. Encrypt at rest.
- Add an SMTP test-send button on save in the redesign.

---

## Save default property settings

**ID:** `ADMIN.SYSCONFIG.PROPERTY_DEFAULTS_SAVE`
**Trigger:** Save button on the Default Property Settings tab (`Configuration.razor:723`).
**Actor:** Admin.
**Legacy locus:** SP `SP_CRUD_VillaConfigPropertyDefault`.

### Inputs
General:
- `AvailabilityStatus` (default property availability status)
- `IsBookingsRequirePreApproval` (bool)
- `PricesEnteredType` (per-night / per-stay enum)
- `CurrencyId` (default pricing currency)
- `CommissionType`, `CommissionAmount`
- `strCheckinTime`, `strCheckOutTime` (24-hour strings, parsed via `TimeSpan.TryParse`)
- `ChangeOverDay` (day-of-week enum)
- `MinimumNightsRental` (decimal)

Payment schedule defaults (the 3-tier system):
- Deposit: `IsDepositRequired`, `DepositType`, `DepositAmount`
- Interim: `IsInterimRequired`, `InterimType`, `InterimAmount`
- Days-before-arrival: `DaysInterimDueBeforeArrival`, `DaysBalanceDueBeforeArrival`

Security deposit defaults:
- `SecurityDepositRequired`, `SecurityDepositAmountType`, `SecurityDepositAmount`
- `SecurityDepositCalculateFrom`, `SecurityDepositDaysDefundedAfterDeparture` `[TYPO]` (intended `Refunded`)

### Process
1. `SP_CRUD_VillaConfigPropertyDefault` with `@Action=INSERT` (the form only writes; SP handles upsert via singleton-row pattern).
2. These values are consumed by every property workflow that has `IsDefaultSetting*` flags. When a property carries `IsDefaultTax=true`, the resolver pulls `TaxPercentage` from this row.

### Outputs / side effects
- **DB write:** `VillaConfigPropertyDefault` (effectively a singleton).
- **Global impact:** every new property and every existing property whose `IsDefault*` flag is `true` inherits the new value.

### Failure modes
- Invalid time strings parse to `00:00:00` silently.

### Open questions
- The "null means inherit" pattern from the Django redesign (`../03-finance-config.md`) is materially cleaner than the flag-pair pattern here. This entire table maps to a `properties.SystemDefaults` singleton with nullable fields and an `effective_*()` resolver.

---

## Trigger full sync to all configured websites

**ID:** `ADMIN.SYSCONFIG.MANUAL_FULL_SYNC`
**Trigger:** "Sync" button at the top of `/config` (`Configuration.razor:16, 749`).
**Actor:** Admin.
**Legacy locus:** `ApiService.StartResSyncProcess(user, UserId)`.

### Process
Invokes the full sync orchestration sequence — see `11-integrations/public-website-sync.md` → `INTEGRATIONS.PUBLIC_API.FULL_SYNC_ORCHESTRATION`. Logs to `ResLogFile`.

### Outputs / side effects
- 13 sequential API pushes to each configured WordPress site (countries, regions, collections, features, villas, alternatives, rooms, villa features, collection-villa map, nearby, images, descriptions).
- **No progress indicator** in the UI — the toast only shows the final result.
