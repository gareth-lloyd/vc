# Contact ↔ Property Assignment

How a contact is attached to a property with a role, access flags, and notification preferences. The mapping row (`VillaContactMapping`) carries the bulk of the per-property contact behaviour.

## Assign contact to property

**ID:** `DIRECTORY.CONTACT_PROPERTY.ASSIGN`
**Trigger:** Either:
- From the Contact view: select properties in dropdown → Save (`Contacts.razor:420-444`)
- From `PropertyContacts.razor`: select a contact → set roles → Save (`PropertyContacts.razor:514-552`)
**Actor:** Admin.
**Legacy locus:** `PropertyService.cs:1445-1480` (`ModifyVillaContactMapping`); SP `sp_villaContactMapping`.

### Inputs
On the contact-first path:
- `ContactId`, `SelectedProperties` (multi-select; iterates and creates one mapping per property)

On the property-first path:
- `VillaId`, `ContactId`, all role and flag fields below

Mapping fields (set on every assign):
- `RoleId` (string — comma-delimited role ids; e.g. `"1,3"` for Owner + Manager)
- `IsPrimaryContact`, `IsCC`, `IsGroupContact`, `GroupId`, `Notes`
- Access flags: `IsAccessInfo`, `IsAccessAvail`, `IsAccessRates`, `IsAccessBooking`, `IsAccessConfirmAuth`, `IsAccessSlip`
- Notify flags: `IsNotifyInfo`, `IsNotifyAvail`, `IsNotifyRates`, `IsNotifyBooking`, `IsNotifyConfirmReq`, `IsNotifySlip`

### Process
1. `PropertyService.ModifyVillaContactMapping(args)` builds 20+ parameters via `GetPropertyContactParam()` (`PropertyService.cs:1516-1544`).
2. Execute `sp_villaContactMapping` with `@Action=INSERT` or `UPDATE`.

### Outputs / side effects
- **DB write:** `VillaContactMapping` row.
- **DB write (cascading):** `VillaContactRoleMapping` parsed from `RoleId` string.
- Toast "Property contacts saved!".

### Failure modes
- Missing contact in the property-first path → UI rejection.
- FK violations → SP errors caught and surfaced as generic message.

### Open questions
- Two paths (contact-first vs property-first) produce slightly different result sets. Standardise on the property-first path in the redesign.

---

## Set primary contact for property

**ID:** `DIRECTORY.CONTACT_PROPERTY.SET_PRIMARY`
**Trigger:** Check icon in the Primary Contact column on `PropertyContacts.razor:43-50`.
**Actor:** Property manager.

### Process
1. `Model.Args.IsPrimaryContact = true`.
2. `SavePropertyContactsAsync(DbAction.UPDATE)` → `sp_villaContactMapping @Action=UPDATE`.

### Outputs / side effects
- `VillaContactMapping.IsPrimaryContact = true` for the chosen row.
- The SP **should** clear `IsPrimaryContact` on other contacts for the same property — not verified in committed code.

### Failure modes
- Multiple primary contacts possible if the SP doesn't enforce uniqueness.

### Open questions
- Enforce single-primary-per-property in the DB (partial unique index `WHERE is_primary`).

---

## Mark contact as CC (and send booking-confirmation email)

**ID:** `DIRECTORY.CONTACT_PROPERTY.MARK_CC`
**Trigger:** Check icon in the Copied column for a non-owner mapping (`PropertyContacts.razor:577-605`).
**Actor:** Property manager.

### Process
1. Validate email is non-empty.
2. Set `Action = UPDATE_STATUS`, `IsCC = true`.
3. `ResService.SentBookingConfirmEmail(args)` (see `03-catalog/property-features.md` for the email send).
4. `PropertyService.ModifyVillaContactMapping(args)` to persist the flag.

### Outputs / side effects
- **DB write:** `VillaContactMapping.IsCC = true`.
- **Email out:** to the contact (template `enquire_auto_replay_email` — repurposed; see `03-catalog/property-features.md`).

### Failure modes
- Empty email → toast error, no email sent, no DB write.
- SMTP failure → caught; flag may still be persisted.

---

## Detach contact from property

**ID:** `DIRECTORY.CONTACT_PROPERTY.REMOVE`
**Trigger:** Trash icon on `PropertyContacts.razor:498-505`.
**Actor:** Property manager.

### Process
1. Confirm modal.
2. `PropertyService.ModifyVillaContactMapping(args)` with `Action=DELETE`.
3. SP **hard-deletes** the mapping row and cascade-deletes related `VillaContactRoleMapping` rows.

### Outputs / side effects
- **DB write:** mapping row gone.
- Underlying `VillaContact` survives.

### Open questions
- Hard delete vs the soft-delete pattern used elsewhere is inconsistent. Pick one.

---

## List property contacts

**ID:** `DIRECTORY.CONTACT_PROPERTY.LIST`
**Trigger:** `PropertyContacts.razor` initialization (`:334-376`).
**Actor:** Property manager.

### Process
1. Args set with `Action=SELECT_ALL`, `VillaId`, optional `IsGroupContact` flag, optional `GroupId`.
2. Execute `sp_villaContactMapping @Action=SELECT_ALL`.
3. Result enriched with computed `Name`, `Company`, `Role(s)`, `IsPrimaryContact`, `IsCC`, `Notes`.

### Outputs / side effects
- Grid populated.
