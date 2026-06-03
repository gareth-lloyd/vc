import { z } from "zod";
import { paginated } from "@/lib/api/pagination";
import { userMeSchema } from "@/features/auth/schemas";

// ----------------------------------------------------------------------
// /owner/me — owner detection + per-property grants
// ----------------------------------------------------------------------

export const ownerPropertyGrantSchema = z.object({
  property_id: z.number(),
  view_full_money: z.boolean(),
  view_guest_details: z.boolean(),
});
export type OwnerPropertyGrant = z.infer<typeof ownerPropertyGrantSchema>;

export const ownerOrganisationSchema = z.object({
  id: z.number(),
  name: z.string(),
  role: z.string(),
  properties: z.array(ownerPropertyGrantSchema),
});
export type OwnerOrganisation = z.infer<typeof ownerOrganisationSchema>;

export const ownerMeSchema = z.object({
  user: userMeSchema,
  is_owner: z.literal(true),
  organisations: z.array(ownerOrganisationSchema),
});
export type OwnerMe = z.infer<typeof ownerMeSchema>;

// ----------------------------------------------------------------------
// /owner/dashboard
// ----------------------------------------------------------------------

export const ownerUpcomingArrivalSchema = z.object({
  reference: z.string(),
  property_id: z.number(),
  property_name: z.string().nullable(),
  date_from: z.string(),
  date_to: z.string(),
  guest_name: z.string().nullable(),
  adults: z.number(),
  children: z.number(),
});
export type OwnerUpcomingArrival = z.infer<typeof ownerUpcomingArrivalSchema>;

export const ownerDashboardSchema = z.object({
  ytd: z.object({
    bookings: z.number(),
    // Null when the owner has no view_full_money grant anywhere.
    gross_revenue: z.string().nullable(),
    net_to_owner: z.string().nullable(),
  }),
  properties: z.object({
    total: z.number(),
    by_status: z.record(z.string(), z.number()),
  }),
  upcoming_arrivals: z.array(ownerUpcomingArrivalSchema),
});
export type OwnerDashboard = z.infer<typeof ownerDashboardSchema>;

// ----------------------------------------------------------------------
// /owner/properties
// ----------------------------------------------------------------------

export const ownerPropertySchema = z.object({
  id: z.number(),
  name: z.string(),
  display_name: z.string().nullable(),
  slug: z.string(),
  status: z.string(),
  category: z.number().nullable(),
  group: z.number().nullable(),
  region: z.number().nullable(),
  guests: z.number().nullable(),
  bedrooms: z.number().nullable(),
  hero_image_url: z.string().nullable(),
  // True when the caller's role on this villa permits requesting blocks.
  can_request_block: z.boolean(),
});
export type OwnerProperty = z.infer<typeof ownerPropertySchema>;

export const ownerPropertiesResponseSchema = paginated(ownerPropertySchema);

// ----------------------------------------------------------------------
// /owner/bookings — money + guest_contact fields are redaction-optional:
// the keys are simply ABSENT when the property grant doesn't permit them.
// ----------------------------------------------------------------------

export const ownerGuestCountrySchema = z.object({
  code: z.string(),
  name: z.string(),
});
export type OwnerGuestCountry = z.infer<typeof ownerGuestCountrySchema>;

export const ownerBookingListItemSchema = z.object({
  id: z.number(),
  reference: z.string(),
  status: z.string(),
  property_id: z.number().nullable(),
  property_name: z.string().nullable(),
  date_from: z.string(),
  date_to: z.string(),
  adults: z.number(),
  children: z.number(),
  currency_code: z.string().nullable(),
  guest_name: z.string().nullable(),
  guest_country: ownerGuestCountrySchema.nullable(),
  is_repeat_guest: z.boolean(),
  // Capability flag: may this caller approve/decline the booking (role-scoped)?
  can_approve: z.boolean(),
  // view_full_money grant only — absent otherwise.
  rental_price: z.string().optional(),
  balance_due: z.string().optional(),
});
export type OwnerBookingListItem = z.infer<typeof ownerBookingListItemSchema>;

export const ownerBookingsResponseSchema = paginated(ownerBookingListItemSchema);

export const ownerGuestContactSchema = z.object({
  email: z.string(),
  phone: z.string(),
});
export type OwnerGuestContact = z.infer<typeof ownerGuestContactSchema>;

export const ownerBookingDetailSchema = ownerBookingListItemSchema.extend({
  // view_full_money grant only.
  gross_total: z.string().optional(),
  commission: z.string().optional(),
  net_to_owner: z.string().optional(),
  // view_guest_details grant only.
  guest_contact: ownerGuestContactSchema.optional(),
});
export type OwnerBookingDetail = z.infer<typeof ownerBookingDetailSchema>;

// ----------------------------------------------------------------------
// Owner block requests
// ----------------------------------------------------------------------

export const ownerBlockKindSchema = z.enum(["owner_stay", "maintenance", "other"]);
export type OwnerBlockKind = z.infer<typeof ownerBlockKindSchema>;

export const ownerBlockRequestStatusSchema = z.enum([
  "pending",
  "approved",
  "declined",
  "cancelled",
]);
export type OwnerBlockRequestStatus = z.infer<typeof ownerBlockRequestStatusSchema>;

export const ownerBlockRequestSchema = z.object({
  id: z.number(),
  property: z.number(),
  date_from: z.string(),
  date_to: z.string(),
  kind: ownerBlockKindSchema,
  notes: z.string(),
  status: ownerBlockRequestStatusSchema,
  review_note: z.string(),
  reviewed_at: z.string().nullable(),
  created_at: z.string(),
});
export type OwnerBlockRequest = z.infer<typeof ownerBlockRequestSchema>;

export const ownerBlockRequestsResponseSchema = z.array(ownerBlockRequestSchema);

// Write input — `date_to` must be strictly after `date_from` (matches the
// backend serializer + DB constraint). The refine message is an i18n key.
export const blockRequestWriteInputSchema = z
  .object({
    property: z.number(),
    date_from: z.string().min(1, "blocks.errors.required"),
    date_to: z.string().min(1, "blocks.errors.required"),
    kind: ownerBlockKindSchema,
    notes: z.string(),
  })
  .refine((v) => v.date_to > v.date_from, {
    path: ["date_to"],
    message: "blocks.errors.date_to_after_from",
  });
export type BlockRequestWriteInput = z.infer<typeof blockRequestWriteInputSchema>;

// ----------------------------------------------------------------------
// /owner/properties/{id}/calendar
// ----------------------------------------------------------------------

export const ownerCalendarSegmentSchema = z.object({
  available: z.boolean(),
  reason: z.string().nullable(),
});

export const ownerCalendarCellSchema = z.object({
  date: z.string(),
  available: z.boolean(),
  reason: z.string().nullable(),
  segments: z
    .object({
      am: ownerCalendarSegmentSchema,
      pm: ownerCalendarSegmentSchema,
    })
    .optional(),
});
export type OwnerCalendarCell = z.infer<typeof ownerCalendarCellSchema>;

export const ownerCalendarSchema = z.object({
  property_id: z.number(),
  // True when the caller's role on this villa permits requesting blocks.
  can_request_block: z.boolean(),
  cells: z.array(ownerCalendarCellSchema),
});
export type OwnerCalendar = z.infer<typeof ownerCalendarSchema>;

export interface OwnerBookingFilters {
  ordering?: string;
  page?: number;
}

export interface OwnerBlockRequestFilters {
  property?: number;
  status?: OwnerBlockRequestStatus;
}
