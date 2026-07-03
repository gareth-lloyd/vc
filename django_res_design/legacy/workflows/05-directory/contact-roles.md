# Contact Roles

Role assignment on property↔contact mappings, plus the reference-data loaders for the role/group multi-selects.

## Change roles on a property mapping

**ID:** `DIRECTORY.CONTACT_ROLE.UPDATE_MAPPING`
**Trigger:** Role multi-select change on a property contact row (`Contacts.razor:451-461`, `PropertyContacts.razor:507`).
**Actor:** Property manager.
**Legacy locus:** `PropertyService.ModifyVillaContactMapping`.

### Inputs
- Mapping `Id`
- New `RoleId` (comma-delimited string of role ids — produced from the multi-select via `string.Join(',', args.Select(x => x.Id))`)

### Process
1. Locate the in-memory mapping by id; update `SelectedRoles`.
2. Call `ModifyVillaContactMapping(VillaContactMapping { Id, RoleId })`.
3. SP rewrites `VillaContactMapping.RoleId` plus the `VillaContactRoleMapping` junction rows (typically delete+reinsert based on the comma string).

### Outputs / side effects
- **DB write:** mapping row + junction rows.
- UI refreshes grid row.

### Open questions
- Two storage shapes for the same data (comma string + junction). Pick the junction; the comma is a denormalised cache that drifts.

---

## Fetch roles for multi-selects

**ID:** `DIRECTORY.LOOKUP.GET_ROLES`
**Trigger:** Page initialisation on Contacts / NewContact / PropertyContacts.
**Actor:** System.
**Legacy locus:** `ResService.cs:1225-1238` (`GetRoles`); SP `sp_getRoles`.

### Process
1. Execute `sp_getRoles`.
2. Returns `List<VillaGroups>` with `Id` and `Name`.

### Outputs / side effects
- Used to populate the role dropdowns.

---

## Fetch groups for multi-selects

**ID:** `DIRECTORY.LOOKUP.GET_GROUPS`
**Trigger:** Page initialisation.
**Actor:** System.
**Legacy locus:** `ResService.cs:1199-1222` (`GetGroups`); SP `sp_getGroups`.

### Process
1. Execute `sp_getGroups` with pagination.
2. Returns `List<VillaGroups>`.

### Open questions
- Roles and Groups currently both come from `VillaGroup` table — see the table-sharing concern called out in `02-administration/product-taxonomy.md`. The split needs to happen at the table level, after which these loaders become loaders for separate models.
