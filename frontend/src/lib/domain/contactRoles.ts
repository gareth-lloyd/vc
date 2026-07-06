// Neutral home for the property contact-role vocabulary (GAP-072). Both
// properties (the assignment schema/dialog) and contacts (the Suppliers role
// column, which allowlists genuine property roles) need this set; homing it
// here breaks the last thin contacts→properties edge. Mirrors the backend
// `accounts.ContactRole` enum (`django_res/accounts/enums.py`).
// features/properties/schemas.ts re-exports it and builds the Zod enum on top.
export const PROPERTY_CONTACT_ROLES = [
  "owner",
  "manager",
  "agent",
  "villa_admin",
  "management_company",
  "housekeeper",
  "owners_rep",
] as const;
