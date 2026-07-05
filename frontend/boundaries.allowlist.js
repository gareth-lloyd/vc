// GAP-063 shrink-only ratchet of pre-existing feature→feature imports — see
// CLAUDE.md "Module boundaries". Entries may only be REMOVED (or relabelled
// when shared code moves to its true home feature), never added; liveness is
// enforced by src/test/boundaries.test.ts.
export const ALLOWED_EDGES = {
  admin: ["users"],
  auth: ["owner-portal"],
  availability: ["admin", "properties"],
  bookings: ["audit", "auth"],
  // clients→availability relabelled to clients→properties when the geo hooks
  // (useRegions/useCollections) moved to their true home (GAP-063 Unit 3).
  clients: ["contacts", "properties"],
  companies: ["audit"],
  contacts: ["audit", "bookings", "companies", "enquiries", "properties"],
  dashboard: ["bookings", "enquiries"],
  enquiries: ["bookings", "contacts", "quotations", "users"],
  "owner-portal": ["auth"],
  properties: ["admin", "audit", "contacts"],
  quotations: ["admin", "bookings", "contacts", "enquiries", "properties"],
};
