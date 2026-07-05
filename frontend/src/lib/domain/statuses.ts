// Neutral home for status enums shared across features (GAP-063): contacts
// renders booking/enquiry history and reuses the org enums for its nested
// agency_detail. This lift fully pays down the contacts→enquiries edge;
// contacts→bookings and contacts→companies survive deliberately (contacts
// still imports bookingStatusLabel from bookings and Company UI pieces from
// companies — deferred pay-down, see the ratchet). Owner features re-export
// for intra-feature use; options lists and terminal sets stay with their
// owners.
import { z } from "zod";
import i18n from "@/i18n";

export const bookingStatusSchema = z.enum([
  "draft",
  "pending_owner_approval",
  "awaiting_deposit",
  "deposit_paid",
  "awaiting_balance",
  "balance_paid",
  "checked_in",
  "checked_out",
  "cancelled",
  "expired",
  "declined",
]);
export type BookingStatus = z.infer<typeof bookingStatusSchema>;

export const enquiryStatusSchema = z.enum([
  "new",
  "progressing",
  "quote_sent",
  "follow_up",
  "dead",
  "converted",
]);
export type EnquiryStatus = z.infer<typeof enquiryStatusSchema>;

export function enquiryStatusLabel(status: EnquiryStatus): string {
  return i18n.t(`enquiries:labels.status.${status}`);
}

// The serialized agency value is "agency"; the other org types ("mgmt",
// "supplier") are accepted on read so the detail/list schemas never reject a
// row, even though the companies UI only ever creates/filters agencies.
export const orgTypeSchema = z.enum(["agency", "mgmt", "supplier"]);
export type OrgType = z.infer<typeof orgTypeSchema>;

export const orgStatusSchema = z.enum(["active", "inactive"]);
export type OrgStatus = z.infer<typeof orgStatusSchema>;
