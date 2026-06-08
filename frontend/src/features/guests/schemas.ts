import { z } from "zod";
import { paginated } from "@/lib/api/pagination";
import { bookingStatusSchema } from "@/features/bookings/schemas";
import { enquiryStatusSchema } from "@/features/enquiries/schemas";

export const guestStatusSchema = z.enum(["active", "archived", "anonymized"]);
export type GuestStatus = z.infer<typeof guestStatusSchema>;

// ContactMethod is the same shared enum the enquiry capture form uses; kept as
// a local 3-value enum here rather than coupling guests → enquiries for it.
export const guestContactMethodSchema = z.enum(["email", "phone", "sms"]);
export type GuestContactMethod = z.infer<typeof guestContactMethodSchema>;

export const guestSchema = z.object({
  id: z.number(),
  first_name: z.string(),
  last_name: z.string(),
  title: z.string().nullable().optional(),
  // Email is optional on the backend now — absence is null, never a synthetic.
  email: z.string().nullable(),
  phone: z.string().optional().default(""),
  contact_method: guestContactMethodSchema.nullable().optional(),
  status: guestStatusSchema,
  created_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
});
export type Guest = z.infer<typeof guestSchema>;

// The booking an enquiry converted to, surfaced on each history row. Null when
// no ACCEPTED quotation's selected line has a live (non-archived) booking.
export const convertedBookingSchema = z.object({
  reference: z.string(),
  status: bookingStatusSchema,
});
export type ConvertedBooking = z.infer<typeof convertedBookingSchema>;

export const guestEnquiryHistorySchema = z.object({
  id: z.number(),
  reference: z.string(),
  status: enquiryStatusSchema,
  site_source: z.string().nullable().optional(),
  request_type: z.string().nullable().optional(),
  created_at: z.string().nullable().optional(),
  quote_count: z.number(),
  converted_booking: convertedBookingSchema.nullable(),
});
export type GuestEnquiryHistoryItem = z.infer<typeof guestEnquiryHistorySchema>;

export const guestsSearchResponseSchema = paginated(guestSchema);
export const guestEnquiryHistoryResponseSchema = paginated(guestEnquiryHistorySchema);
