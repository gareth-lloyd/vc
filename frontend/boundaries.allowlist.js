// GAP-063 shrink-only ratchet of pre-existing feature→feature imports — see
// CLAUDE.md "Module boundaries". Entries may only be REMOVED (or relabelled
// when shared code moves to its true home feature), never added; liveness is
// enforced by src/test/boundaries.test.ts.
export const ALLOWED_EDGES = {
  admin: ["users"],
  availability: ["properties"],
  bookings: ["audit", "auth"],
  clients: ["contacts"],
  companies: ["audit"],
  contacts: ["audit", "bookings", "companies"],
  dashboard: ["bookings", "enquiries"],
  enquiries: ["bookings", "contacts", "users"],
  "owner-portal": ["auth"],
  properties: ["admin", "audit", "contacts"],
  quotations: ["bookings", "contacts", "enquiries", "properties"],
};
