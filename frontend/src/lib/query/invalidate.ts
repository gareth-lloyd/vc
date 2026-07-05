import type { QueryClient } from "@tanstack/react-query";
import { queryKeys, type QuotationId } from "./keys";

// Entity → dependents invalidation map (BUG-018). Mutation success handlers
// route through these helpers instead of hand-listing keys per hook, so a new
// dependent surface is added in exactly one place.
//
// The booking/enquiry helpers deliberately do NOT touch the mutated entity's
// own detail key: their success handlers write the response into the cache
// with setQueryData, and invalidating the same key would refetch what was
// just written. (Quotation status handlers don't setQueryData, so the
// quotation helper does invalidate its own detail.) Activity/notes sub-keys
// are likewise the handler's own business.

/** The full availability picture for one property: its month-grid calendar,
 * holds, bookings-in-range, plus the cross-property timeline/weekly-prices. */
export function invalidatePropertyAvailability(qc: QueryClient, propertyId: number): void {
  void qc.invalidateQueries({ queryKey: queryKeys.properties.availabilityRoot(propertyId) });
  void qc.invalidateQueries({ queryKey: queryKeys.properties.holdsRoot(propertyId) });
  void qc.invalidateQueries({ queryKey: queryKeys.properties.bookingsRoot(propertyId) });
  void qc.invalidateQueries({ queryKey: queryKeys.availability.all() });
}

/** A contact's detail page + sub-tabs (bookings/enquiries/properties/…).
 * Three-state contract, matching how contact FKs appear in API payloads:
 * - `number` — precise: just that contact's subtree;
 * - `undefined` — the contact FK is unknown (absent from the payload): broad
 *   `["contacts","detail"]` prefix; only mounted queries refetch, so cheap.
 *   Never pass `undefined` to mean "skip" — that's what `null` is for;
 * - `null` — the entity is known to have no linked contact: skip. */
export function invalidateContactSubtree(qc: QueryClient, contactId?: number | null): void {
  if (contactId === null) return;
  if (contactId === undefined) {
    void qc.invalidateQueries({ queryKey: queryKeys.contacts.details() });
    return;
  }
  void qc.invalidateQueries({ queryKey: queryKeys.contacts.detail(contactId) });
}

/** Everything a booking change can make stale beyond the booking's own detail:
 * lists, status counts, dashboard, the owning property's availability (when
 * the payload has one — money mutations don't, and they don't move dates) and
 * contact sub-tabs (broad — booking payloads carry no contact FK). */
export function invalidateBookingDependents(
  qc: QueryClient,
  booking?: { property?: number | null },
): void {
  void qc.invalidateQueries({ queryKey: queryKeys.bookings.lists() });
  void qc.invalidateQueries({ queryKey: queryKeys.bookings.statusCountsAll() });
  void qc.invalidateQueries({ queryKey: queryKeys.dashboard.all() });
  if (booking?.property != null) {
    invalidatePropertyAvailability(qc, booking.property);
  }
  invalidateContactSubtree(qc, undefined);
}

/** Everything an enquiry change can make stale beyond its own detail:
 * lists, status counts, dashboard and the linked person's and agent's
 * contact subtrees. */
export function invalidateEnquiryDependents(
  qc: QueryClient,
  enquiry: { person?: number | null; agent?: number | null },
): void {
  void qc.invalidateQueries({ queryKey: queryKeys.enquiries.lists() });
  void qc.invalidateQueries({ queryKey: queryKeys.enquiries.statusCountsAll() });
  void qc.invalidateQueries({ queryKey: queryKeys.dashboard.all() });
  invalidateContactSubtree(qc, enquiry.person);
  invalidateContactSubtree(qc, enquiry.agent);
}

/** The cross-entity surfaces a quotation touches: its parent enquiry and the
 * guest/agent contact subtrees. Split out from the full dependents helper so
 * non-status mutations (line hold/release) can refresh these without churning
 * quotation lists/status counts. */
export function invalidateQuotationRelated(
  qc: QueryClient,
  quotation: { enquiry?: number | null; guest?: number | null; agent?: number | null },
): void {
  if (quotation.enquiry != null) {
    // The detail prefix also covers the enquiry's activity/notes sub-keys.
    void qc.invalidateQueries({ queryKey: queryKeys.enquiries.detail(quotation.enquiry) });
  }
  invalidateContactSubtree(qc, quotation.guest);
  invalidateContactSubtree(qc, quotation.agent);
}

/** Everything a quotation status change can make stale: its own detail
 * (status flips are visible there), lists, status counts, plus the related
 * enquiry and contacts. */
export function invalidateQuotationDependents(
  qc: QueryClient,
  quotation: {
    id: QuotationId;
    enquiry?: number | null;
    guest?: number | null;
    agent?: number | null;
  },
): void {
  void qc.invalidateQueries({ queryKey: queryKeys.quotations.detail(quotation.id) });
  void qc.invalidateQueries({ queryKey: queryKeys.quotations.lists() });
  void qc.invalidateQueries({ queryKey: queryKeys.quotations.statusCountsAll() });
  invalidateQuotationRelated(qc, quotation);
}
