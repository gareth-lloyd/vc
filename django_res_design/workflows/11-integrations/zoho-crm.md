# Zoho CRM Integration

Zoho is the system of record for sales pipeline: enquiries, contacts, villas, quotations, and bookings are mirrored into **custom Zoho modules** (not the built-in Leads/Deals).

## Custom modules in use

| Local concept | Zoho module | Push class |
|---|---|---|
| Enquiry | `VILLA_ENQUIRY` | `ZohoEnquiryPostData` |
| Contact (guest, agent) | `VILLA_MASTER_CONTACT` | `ZohoContactPostData` |
| Villa / Property | `VILLLA_MASTER` `[TYPO]` (intended `VILLA_MASTER`) | `ZohoVillaPostData` |
| Quotation | `VILLA_QUOTATIONS` | `QuotationPostData` |
| Booking | `VILLA_BOOKING` | `BookingPostData` |
| Archived booking | `ARCHIVE_BOOKING` | `BookingPostData` (`Stage="Archive Booking"`) |

## Endpoints

Zoho operates via **Functions** (Deluge scripts addressable by name):
- INSERT/UPDATE: `{ApiUrl}functions/fn_{path}/actions/execute?auth_type=oauth`
- DELETE: `{ApiUrl}functions/fn_delete_recordid/actions/execute?auth_type=oauth`

Specific paths:
- Enquiry: `fn_enquirypath`
- Quotation: `fn_quotepath`
- Booking: `fn_bookingpath`

## Refresh Zoho OAuth access token

**ID:** `INTEGRATIONS.ZOHO.OAUTH_REFRESH`
**Trigger:** On-demand when a request needs a token and the cached one has expired; or at startup.
**Actor:** System.
**Legacy locus:** `ResApiService.cs:1026-1057`; `ZohoConfig.GenerateTokenUrl` at `ZohoConfig.cs:21-24`.

### Inputs
From `ZohoConfig.ZohoSetting`: `ClientId`, `ClientSecret`, `RefereshToken` `[TYPO]`, `TokenUrl`, `ApiUrl`.

### Process
1. Build URL: `{TokenUrl}refresh_token={RefereshToken}&client_id={ClientId}&client_secret={ClientSecret}&grant_type=refresh_token`.
2. HTTP POST via RestSharp (timeout 24h, **3 retries on timeout**).
3. On success: deserialize `ZohoTokenExp`; persist to disk at `Constant.TOKEN_PATH`.

### Outputs / side effects
- File written at `TOKEN_PATH` with `{access_token, scope, api_domain, token_type, expires_in}`.
- Logs full request/response.

### Failure modes
- Token-endpoint down → retries exhausted → next caller picks up an expired token and fails.

### Open questions
- Don't store tokens on disk — keep in memory or use a cache (Redis).

---

## Push enquiry to Zoho

**ID:** `INTEGRATIONS.ZOHO.PUSH_ENQUIRY`
**Trigger:** Background task spawned by `ENQUIRY.INTAKE.WEBSITE` or `ENQUIRY.INTAKE.STAFF`; also called from `QUOTATION.PERSIST.SAVE_MASTER` when `Action=UPDATE_ENQUIRE`.
**Actor:** System (background).
**Legacy locus:** `ResApiService.cs:865-982` (`PushZohoEnqueireAsyncNew` and `PushZohoEnqueireAsync`).

### Inputs
`ZohoEnquiryPostData`:
- **Enquiry** sub-object:
  - `RES_ID` (local enquiry id, string)
  - `Zoho_ID` (existing Zoho id; present on UPDATE)
  - `Name` (concatenated first + last name)
  - `Payment_Contact` (same)
  - `Date_From`, `Date_To` (formatted)
  - `Length_of_Stay` (e.g., `"7 nights"`)
  - `Bedrooms_From`, `Bedrooms_To`
  - `Number_of_Adults`, `Number_of_Children`
  - `Stage` (`ZohoQuoteStage` — default `"NewEnquire"` `[TYPO]`)
  - `Agency`, `Agent`
  - `Owner` (hardcoded `"info@villacollective.com"`)
  - `Enquiry_Notes`
  - `Enquiry_Source` ("From Website Wishlist" / "Website Form on Villa details page" / "Website Form on Landing Page" / manual values from staff path)
  - `Countries_of_Interest`, `Regions_of_Interest` (comma-separated)
  - `Where_did_you_hear_from_us`
- **Account**: `Name` (full guest name)
- **Contact**: `Email`, `First_Name`, `Last_Name`, `Phone` (`"{CountryCode} {PhoneNumber}"`)
- **Villa**: `Name` (when a specific property is requested)
- **Debug_Recipients** (hardcoded test addresses)

### Process
1. Ensure OAuth token valid (refresh if needed via `INTEGRATIONS.ZOHO.OAUTH_REFRESH`).
2. Endpoint: `fn_enquirypath` (UPSERT) or `fn_delete_recordid` (DELETE).
3. HTTP POST with `Zoho-oauthtoken` header.
4. Response shape:
   ```
   { debug: [ { status: "success" | "failure", reason: { Zoho_Id, message } } ] }
   ```
5. On success, persist Zoho id via `exec sp_updateZohoId {resId}, '{zohoId}', 'VILLA_ENQUIRY'`.

### Outputs / side effects
- **External:** Zoho `VILLA_ENQUIRY` module record created/updated.
- **DB write:** `VillaEnquire.ZohoId` populated via `sp_updateZohoId`.
- **Log file:** full request/response to disk.

### Failure modes
- No retry on failure.
- Background task — silent failure if Zoho is down.

### Open questions
- The `Stage="NewEnquire"` typo (missing 'd') will probably round-trip back as-is from Zoho since Zoho stores whatever you send.

---

## Push contact to Zoho

**ID:** `INTEGRATIONS.ZOHO.PUSH_CONTACT`
**Trigger:** Contact save/update — though as noted in `05-directory/`, this is not actually wired in committed UI code; only the data shape is defined.
**Actor:** System.
**Legacy locus:** `ResApiService.cs:839-863`; `ZohoContactPostData.cs`.

### Inputs
`ZohoContactPostData`: `id`, `RES_ID`, `Email`, `First_Name`, `Last_Name`, `Full_Name`, `Phone`, `Title`, `Mobile`, `Address_Line_1`.

### Process
- `ZohoRequestAsync` with module `VILLA_MASTER_CONTACT`.
- On success: `sp_updateZohoId(resId, zohoId, 'VILLA_MASTER_CONTACT')`.

### Open questions
- Wire up the actual call site. Currently the data class is dead code.

---

## Push villa/property to Zoho

**ID:** `INTEGRATIONS.ZOHO.PUSH_VILLA`
**Trigger:** Property create/update (via `CATALOG.PROPERTY.UPDATE_OVERVIEW`).
**Actor:** System.
**Legacy locus:** `ResApiService.cs:1001-1024` (`PushZohoVilla`).

### Inputs
`ZohoVillaPostData`: `id`, `Name`, `VillaId`, `CountryName`, `Region`, `Owner`, `Villa_URL`, `Villa_Name_Other`, `Co_ordinates` (lat,long string), `Note`, `Country` (list containing `CountryName`), `Last_Activity_Time`, `Modified_Time`, `Created_Time`.

### Process
- `ZohoRequestAsync` with module `VILLLA_MASTER` `[TYPO]`.
- On success: `sp_updateZohoId(resId, zohoId, 'VILLLA_MASTER')`.

### Open questions
- Fix the module-name typo at migration time.

---

## Push quotation / booking to Zoho

**ID:** `INTEGRATIONS.ZOHO.PUSH_QUOTATION_BOOKING`
**Trigger:** Quotation send (`QUOTATION.TRANSMISSION.SEND_EMAIL`) → module `VILLA_QUOTATIONS`. Booking save (`BOOKING.LIFECYCLE.CREATE_FROM_QUOTATION`) → module `VILLA_BOOKING`. Archive action → module `ARCHIVE_BOOKING`.
**Actor:** System (background).
**Legacy locus:** `ResApiService.cs:985-999` (`PushZohoQuotationAsync`); `ResService.cs:4747-4813` (`PushZohoBooking`).

### Inputs
`BookingPostData` / `QuotationPostData` — a multi-object payload:

**Quote / Booking** object:
- `RES_ID` (local id)
- `Name` (guest name)
- `Stage` ("Draft" / "Sent" / "Accepted" / "Lost" / "Booked" / "Confirmed" / "Archive Booking")
- `Arrival_Date`, `Departure_Date`
- `No_of_Nights`, `No_of_Guests`
- `Valid_Until` (`Departure_Date + 6 days`)
- `Country`, `Region`, `Owner`, `Currency`
- Money: `Deposit_Amount` (initial), `Balance_Amount` (rental), `Interim_Deposit`, `Balance_Due`, `Commission_Total`, `Security_Deposit_Amount`, `Agent_Split_Amount`, `Security_Deposit`, `VC_Commission`, `Net_Booking`, `Cost_of_Sale`
- Billing: `Billing_Street`, `Billing_City`, `Billing_State`, `Billing_Zip`, `Billing_Country`
- `Terms_and_Conditions`
- **Enquiry**: `RES_ID` (link to parent enquiry)
- **Account**: `Name`
- **Contact**: `Email`, `First_Name`, `Last_Name`
- **Villa**: `Name`
- **Line_Items**: `Product_Name`, `Description`, `Quantity`, `List_Price`, `Net_Price`, `Discount`, `Tax`

### Process
1. Look up `vw_VillaFinance` for the villa → commission settings.
2. Extract per-tier payment amounts from `PaymentDetails[]`:
   - Initial Deposit = the row matching `"Deposit"`
   - Balance = row matching `"Balance"`
   - Sec Dep = row matching `"Sec Dep"`
3. Compute commission split (see `08-quotation/persistence.md`).
4. Endpoint: `fn_quotepath` (for quotes) or `fn_bookingpath` (for bookings).
5. POST with `Zoho-oauthtoken`.
6. Log payload + Zoho id to file `zoho_booking_post_data` (or `zoho_quotation_…`).

### Outputs / side effects
- **External:** Zoho record in the chosen module.
- **DB write:** Zoho id stored back (`VillaQuotationMaster.ZohoId` / `VillaBooking.ZohoId`).
- **Async**, non-blocking.

### Failure modes
- Same general issues as enquiry push: no retry, silent failure.

### Open questions
- The Stage→module relationship should be made explicit (e.g., always use `VILLA_BOOKING` and let `Stage="Archive"` filter Zoho-side views, rather than duplicating into `ARCHIVE_BOOKING`).
