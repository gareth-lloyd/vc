import { z } from "zod";
import { paginated } from "@/lib/api/pagination";

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

export const bookingListItemSchema = z.object({
  id: z.number(),
  reference: z.string(),
  status: bookingStatusSchema,
  property: z.number(),
  guest: z.number(),
  agent: z.number().nullable().optional(),
  assigned_to: z.number().nullable().optional(),
  date_from: z.string(),
  date_to: z.string(),
  adults: z.number(),
  children: z.number().default(0),
  currency: z.number(),
  rental_price: z.string(),
  balance_due: z.string(),
  balance_due_at: z.string().nullable().optional(),
  site_source: z.string(),
  is_archived: z.boolean().optional().default(false),
  archived_at: z.string().nullable().optional(),
  created_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),

  property_name: z.string().nullable().optional(),
  guest_name: z.string().nullable().optional(),
  guest_email: z.string().nullable().optional(),
  currency_code: z.string().nullable().optional(),
  total: z.string().nullable().optional(),
  night_count: z.number().nullable().optional(),
});
export type BookingListItem = z.infer<typeof bookingListItemSchema>;

export const bookingDetailSchema = bookingListItemSchema.extend({
  quotation_line: z.number().nullable().optional(),
  pricing_snapshot: z.unknown().optional(),
  discount: z.string().nullable().optional(),
  adjustment: z.string().nullable().optional(),
  terms_version: z.number().nullable().optional(),
  terms_accepted_at: z.string().nullable().optional(),
  payment_method: z.string().nullable().optional(),
  cancel_reason: z.string().nullable().optional(),
  cancelled_at: z.string().nullable().optional(),
});
export type BookingDetail = z.infer<typeof bookingDetailSchema>;

export const bookingListResponseSchema = paginated(bookingListItemSchema);

export const bookingEventSchema = z.object({
  id: z.number(),
  booking: z.number().optional(),
  from_status: z.string().nullable(),
  to_status: z.string(),
  actor: z.number().nullable().optional(),
  source: z.string(),
  reason: z.string().optional().default(""),
  meta: z.record(z.string(), z.unknown()).optional().default({}),
  created_at: z.string(),
});
export type BookingEvent = z.infer<typeof bookingEventSchema>;

export const bookingActivityResponseSchema = paginated(bookingEventSchema);

export const bookingNoteKindSchema = z.enum(["general", "internal", "concierge", "villa"]);
export type BookingNoteKind = z.infer<typeof bookingNoteKindSchema>;

export const bookingNoteVisibilitySchema = z.enum(["staff_only", "owner", "guest"]);
export type BookingNoteVisibility = z.infer<typeof bookingNoteVisibilitySchema>;

export const bookingNoteSchema = z.object({
  id: z.number(),
  booking: z.number().optional(),
  author: z.number().nullable().optional(),
  kind: bookingNoteKindSchema,
  body: z.string(),
  is_pinned: z.boolean().optional().default(false),
  visibility: bookingNoteVisibilitySchema,
  created_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
});
export type BookingNote = z.infer<typeof bookingNoteSchema>;

export const bookingNotesResponseSchema = paginated(bookingNoteSchema);

export const bookingNoteWriteInputSchema = z.object({
  kind: bookingNoteKindSchema,
  visibility: bookingNoteVisibilitySchema,
  body: z.string().trim().min(1, "Body is required").max(10_000),
  is_pinned: z.boolean(),
});
export type BookingNoteWriteInput = z.infer<typeof bookingNoteWriteInputSchema>;

export const BOOKING_NOTE_KIND_LABELS: Record<BookingNoteKind, string> = {
  general: "General",
  internal: "Internal",
  concierge: "Concierge",
  villa: "Villa",
};

export const BOOKING_NOTE_VISIBILITY_LABELS: Record<BookingNoteVisibility, string> = {
  staff_only: "Staff only",
  owner: "Owner",
  guest: "Guest",
};

export const BOOKING_NOTE_KIND_OPTIONS = bookingNoteKindSchema.options.map((value) => ({
  value,
  label: BOOKING_NOTE_KIND_LABELS[value],
}));

export const BOOKING_NOTE_VISIBILITY_OPTIONS = bookingNoteVisibilitySchema.options.map((value) => ({
  value,
  label: BOOKING_NOTE_VISIBILITY_LABELS[value],
}));

export const cancelBookingInputSchema = z.object({
  reason: z.string().trim().max(500, "Keep it under 500 characters").optional(),
});
export type CancelBookingInput = z.infer<typeof cancelBookingInputSchema>;

export const bookingConciergeItemSchema = z.object({
  id: z.number(),
  booking: z.number().optional(),
  tier: z.string(),
  name: z.string(),
  description: z.string().optional().default(""),
  quantity: z.number(),
  unit: z.string(),
  unit_price: z.string(),
  currency: z.number(),
  status: z.string(),
  notes: z.string().optional().default(""),
});
export type BookingConciergeItem = z.infer<typeof bookingConciergeItemSchema>;

export const bookingConciergeItemsResponseSchema = paginated(bookingConciergeItemSchema);

export interface BookingFilters {
  q?: string;
  status?: BookingStatus;
  site?: string;
  ordering?: string;
  page?: number;
}

const BOOKING_STATUS_LABELS: Record<BookingStatus, string> = {
  draft: "Draft",
  pending_owner_approval: "Pending owner",
  awaiting_deposit: "Awaiting deposit",
  deposit_paid: "Deposit paid",
  awaiting_balance: "Awaiting balance",
  balance_paid: "Balance paid",
  checked_in: "Checked in",
  checked_out: "Checked out",
  cancelled: "Cancelled",
  expired: "Expired",
  declined: "Declined",
};

export const BOOKING_STATUS_OPTIONS = bookingStatusSchema.options.map((value) => ({
  value,
  label: BOOKING_STATUS_LABELS[value],
}));
