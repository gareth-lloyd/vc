// Feature→feature import ratchet — see CLAUDE.md "Module boundaries". Every
// cross-feature edge is enumerated here; eslint (eslint.config.js) errors on
// any import not listed, and src/test/boundaries.test.ts fails if a listed edge
// goes stale. Two tiers (GAP-072):
//
//   SANCTIONED_EDGES — stable, intentional architecture: a feature composing a
//   genuinely downstream feature (audit-trail widget, user/contact pickers, a
//   dashboard aggregating its sources). NOT expected to shrink; an entry
//   changes only with a documented decision.
//
//   DEBT_EDGES — coupling we still intend to pay down. Shrink-only: entries may
//   be removed as the debt is cleared, never added.
//
// Both tiers are liveness-tested. New cross-feature needs never add an edge —
// they go to src/lib/domain, src/lib/geo, or src/components.

export const SANCTIONED_EDGES = {
  admin: ["users"], // user-management page lists and edits users
  availability: ["properties"], // the calendar is a view over properties
  bookings: ["audit", "auth"], // audit-trail widget; auth role-gate
  companies: ["audit"], // audit-trail widget
  contacts: ["audit", "companies"], // audit widget; a contact belongs to an org
  dashboard: ["bookings", "enquiries"], // dashboard aggregates downstream work
  enquiries: ["contacts", "users"], // customer panel; assignee pickers
  "owner-portal": ["auth"], // downstream auth flow
  properties: ["admin", "audit", "contacts"], // tags/currencies taxonomy; audit; people mgmt
  quotations: ["contacts", "enquiries", "properties"], // customer pickers; quote is downstream of its enquiry; searches properties
};

export const DEBT_EDGES = {
  // ReasonFormDialog is reused from bookings — a generic dialog mis-homed in a
  // feature; it belongs in src/components. Pay down by moving it there.
  enquiries: ["bookings"],
  // bookingDetailSchema is read from bookings; the shape lift into lib/domain
  // is pending GAP-062 (schema codegen) so it isn't extracted twice.
  quotations: ["bookings"],
};

// Union the two tiers per source feature — eslint.config.js consumes this
// merged map, so rule generation stays tier-agnostic.
function mergeEdges(...maps) {
  const merged = {};
  for (const map of maps) {
    for (const [from, targets] of Object.entries(map)) {
      merged[from] = [...(merged[from] ?? []), ...targets];
    }
  }
  return merged;
}

export const ALLOWED_EDGES = mergeEdges(SANCTIONED_EDGES, DEBT_EDGES);
