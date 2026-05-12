# Contact Records

CRUD on standalone contact records (`VillaContact`), independent of any property mapping.

## Create contact

**ID:** `DIRECTORY.CONTACT.CREATE`
**Trigger:** Save on `Pages/Contacts/NewContact.razor`.
**Actor:** Admin / staff.
**Legacy locus:** `NewContact.razor:118-228`; `ResService.cs:1686-1720` (`ModifyContact`); SP `sp_contacts`.

### Inputs
- `Title`, `FirstName`, `LastName`, `Company` (validation: FirstName/LastName/Company non-null at form level)
- `Email` (regex-validated: `^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$`)
- `CountryCode`, `MobileNo`
- `AddressLine1`, `AddressLine2`
- `WebsiteUrl`
- `SelectedPrefferedMethod` `[TYPO]` (enum: 0=Unknown, 10=Email, 20=Phone, 30=WhatsApp, 40=Text)
- `SelectedRoles` (multi-select from `VillaGroups` as roles → comma-delimited `RoleId`)
- `SelectedGroups` (multi-select `VillaGroups` → comma-delimited `GroupId`)
- `ZohoId` (optional external ref)
- `Notes`

### Process
1. UI-level validation of email + required fields.
2. `ResService.ModifyContact(args)` builds 20 `DBSQLParameter`s via `GetContactParams()` (`ResService.cs:1853-1879`).
3. **Uniqueness pre-check on Email** via `sp_contacts @Action=SELECTEXITS`. Error: `"Email {email} is already exist"`.
4. Execute `sp_contacts @Action=INSERT`. Returns `@ContactId`.
5. SP also writes child rows:
   - `VillaContactEmail` (primary email duplicated here for the multi-email pattern)
   - `VillaContactTele` (primary phone)
   - `VillaContactGroupMap` rows for each selected group
   - `VillaContactRoleMapping` rows parsed from `RoleId` string

### Outputs / side effects
- **DB write:** `VillaContact` + child junctions.
- **No outbound sync** (Zoho sync is defined but not wired in committed code).
- Toast in admin UI; contact list refreshes.

### Data transformations for storage
- Multi-select role/group lists → comma-delimited strings → split by SP.
- `CreateAt = NOW()`, `CreateBy = current user id`.

### Failure modes
- Email format invalid → form rejection (`NewContact.razor:181-184`).
- Duplicate email → SP error message returned.
- Missing required fields → form rejection.

### Open questions
- Email uniqueness is enforced application-side only. Add a DB unique constraint in the redesign (with sensible scoping if duplicates are legitimate, e.g. distinct kinds of contact).
- Multi-email and multi-phone child tables exist but the UI only manages the primary — the others are dead data.

---

## Edit contact

**ID:** `DIRECTORY.CONTACT.UPDATE`
**Trigger:** Pencil icon → load contact into form → save.
**Actor:** Admin / staff.
**Legacy locus:** `Contacts.razor:254-308` (load), `NewContact.razor:174` (save with `Action=UPDATE`).

### Process
1. Load existing row via `GetAgentById` / `GetClientAgentById` (SP `sp_contacts @Action=SELECT`) → populate form.
2. Save: same path as Create but with `@Action=UPDATE`. Email uniqueness check excludes self.
3. Child rows (roles, groups) are rewritten — delete + reinsert pattern likely (driven by SP).

### Failure modes
- Concurrent edit → last-write-wins; no optimistic concurrency.

---

## Soft-delete contact

**ID:** `DIRECTORY.CONTACT.SOFT_DELETE`
**Trigger:** Trash icon → confirm modal (`Contacts.razor:482-510`).
**Actor:** Admin.
**Legacy locus:** `Contacts.razor:486-510`; SP `sp_contacts @Action=DELETE`.

### Process
1. Confirm modal.
2. `ResService.ModifyContact(args)` with `Action=DELETE`.
3. SP sets `DeletedAt`, `DeletedBy`.

### Outputs / side effects
- **DB write:** `VillaContact.DeletedAt`/`DeletedBy`.
- Contact hidden from lists; existing mappings remain (orphan-pointing-at-deleted).

### Open questions
- Existing `VillaContactMapping` rows that reference a soft-deleted contact are not cleaned up. Decide: cascade soft-delete, or refuse delete while mappings exist.

---

## List / search contacts

**ID:** `DIRECTORY.CONTACT.LIST`
**Trigger:** `/contacts` page load or search-input change.
**Actor:** Authenticated user.
**Legacy locus:** `Contacts.razor:233-251`; SP `sp_getContacts` (parameters `@Skip`, `@Next` = page size, `@Search`).

### Process
1. Execute SP with pagination.
2. Returns `List<VillaContacts>` with computed `Name` (concat), `Email`, `TelePhoneNo`, `Group`, `Roles` strings.

### Outputs / side effects
- Read-only; grid bound to the result.

---

## Fetch contact by id

**ID:** `DIRECTORY.CONTACT.FETCH`
**Trigger:** Edit click; also used inside quotation/booking to load agent or guest.
**Legacy locus:** `ResService.cs:1745-1783` (`GetAgentById`, `GetClientAgentById`); SP `sp_contacts @Action=SELECT`.

### Process
1. Execute SP with `@Id`.
2. Returns a single `VillaContacts` / `AgentDetails`.

### Failure modes
- Returns soft-deleted contacts too — callers should check `DeletedBy IS NULL`.

---

## Search company names

**ID:** `DIRECTORY.CONTACT.SEARCH_COMPANY`
**Trigger:** Used internally by agent autocomplete in quotation/booking flows.
**Legacy locus:** `ResService.cs:1724-1743` (`SearchCompanyByName<T>`); SP `sp_contacts @Action=SELECT_DISTINCT`.

### Process
1. SP returns `List<ResSelectItems<T>>` of distinct company names matching `Company LIKE @args + '%'` (or similar).

### Output
- Used to power the agent-company dropdown on quotations.

---

## Legacy: write `VillaIds` comma-string

**ID:** `DIRECTORY.CONTACT.LEGACY_WRITE_VILLA_IDS`
**Trigger:** Internal — older code path that updates the denormalised `VillaContact.VillaIds` string.
**Legacy locus:** `ResService.cs:1812-1826` (`SaveContactProperties`).

### Process
1. Raw SQL `UPDATE VillaContact SET VillaIds='{villaIds}' WHERE Id = {contactId}` — **SQL injection** `[SECURITY]` if `villaIds` is ever taken unparsed from a client.

### Outputs / side effects
- Writes a stale duplicate of the proper junction.

### Open questions
- Remove this code path and drop the `VillaIds` column in the redesign migration.
