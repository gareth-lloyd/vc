# 05 · Directory

Contact records and their relationships to properties. A contact may be an owner, manager, agent, end guest, or any combination — the role is decided by the property↔contact mapping (`VillaContactMapping`), not by the contact itself.

## Files

| File | Workflows |
|---|---|
| [`contact-records.md`](./contact-records.md) | Create / edit / delete / search / fetch contact records, search by company |
| [`contact-property-assignment.md`](./contact-property-assignment.md) | Assign contact to property, set primary, mark CC, send confirmation email, remove from property, list property contacts |
| [`contact-roles.md`](./contact-roles.md) | Change role multi-select for a property↔contact mapping, manage roles/groups lookup |

## Entities touched

- `VillaContact` — master contact: `Id`, `Title`, `FirstName`, `LastName`, `Company`, `Email`, `CountryCode`, `MobileNo`, `WebsiteUrl`, `PrefferedMethod` `[TYPO]` (intended `PreferredMethod`), `Notes`, `AddressLine1`, `AddressLine2`, `ZohoId`, `OldId`, audit columns, `VillaIds` (legacy comma-delimited string of property ids — duplicated by the proper junction)
- `VillaContactEmail` — per-contact multi-email
- `VillaContactTele` — per-contact multi-phone
- `VillaContactMapping` — junction property↔contact with the **bulk of the access/notify flags**:
  - Access: `IsAccessInfo`, `IsAccessAvail`, `IsAccessRates`, `IsAccessBooking`, `IsAccessConfirmAuth`, `IsAccessSlip`
  - Notify: `IsNotifyInfo`, `IsNotifyAvail`, `IsNotifyRates`, `IsNotifyBooking`, `IsNotifyConfirmReq`, `IsNotifySlip`
  - Role/status: `RoleId` (comma-delimited string), `IsPrimaryContact`, `IsCC`, `IsGroupContact`, `GroupId`, `Notes`
- `VillaContactRoleMapping` — junction `(VillaContactMappingId, RoleId)` (this is a *second* representation of role assignments; the `RoleId` comma string on the mapping itself is also used)
- `VillaContactGroupMap` — junction `(GroupId, ContactId)`

## Stored procedures

- `sp_contacts` (a.k.a. `SP_CONTACTS`) — contact CRUD; supports `INSERT`, `UPDATE`, `DELETE`, `SELECT`, `SELECTEXITS`, `SELECT_DISTINCT` (for company name autocomplete)
- `sp_getContacts` — paginated list with computed columns (`Name`, `Email`, `Group`, `Roles`)
- `sp_villaContactMapping` (a.k.a. `SP_VILLA_CONTACT_MAPPING`) — mapping CRUD; supports `SELECT`, `SELECT_ALL`, `INSERT`, `UPDATE`, `DELETE`, `UPDATE_STATUS`
- `sp_getPropertyContact`, `sp_getContacts_property` — list-by-property variants
- `sp_getGroups`, `sp_getRoles` — reference data loaders

## Cross-cutting notes

- **No Zoho push** captured in the committed code for contacts beyond a defined `ZohoContactPostData` shape — the bidirectional sync is stubbed/incomplete.
- **Legacy `VillaContact.VillaIds`** (comma-delimited property ids) duplicates `VillaContactMapping` — keep only the junction in the Django redesign.
- **`RoleId` stored as comma-delimited string on a mapping** is a half-normalised pattern that coexists with the proper `VillaContactRoleMapping` junction. Pick one.
- **Email validation** is a regex on the client; no DB-level constraint. Multiple contacts may share an email.

## Open design questions for the Django redesign

- The data-model design (`../01-accounts.md`) plans `accounts.Contact`, `accounts.ContactEmail`, `accounts.ContactPhone`, and `accounts.Role` — this maps cleanly.
- The 12 access/notify flags on `VillaContactMapping` look like a half-baked permission system. Replace with a small named-permission set or roles that aggregate them.
- Address-on-contact (`AddressLine1`/`AddressLine2`) is too thin — the legacy quote/booking flows carry a richer address shape (Town, PostCode, Country, etc.) on `EnquireDetails`/`ClientDetails`. Reconcile.
- Bank accounts are currently on `VillaFinance` (the property) rather than on the **owner contact**. Re-attach in the redesign.
