import { z } from "zod";
import i18n from "@/i18n";
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

export const pricingSnapshotLineSchema = z
  .object({
    label: z.string().optional().nullable(),
    description: z.string().optional().nullable(),
    quantity: z.union([z.number(), z.string()]).optional().nullable(),
    unit_price: z.union([z.number(), z.string()]).optional().nullable(),
    total: z.union([z.number(), z.string()]).optional().nullable(),
    kind: z.string().optional().nullable(),
    date: z.string().optional().nullable(),
  })
  .passthrough();
export type PricingSnapshotLine = z.infer<typeof pricingSnapshotLineSchema>;

export const pricingSnapshotSchema = z
  .object({
    property_id: z.union([z.number(), z.string()]).optional().nullable(),
    currency_code: z.string().optional().nullable(),
    date_from: z.string().optional().nullable(),
    date_to: z.string().optional().nullable(),
    lines: z.array(pricingSnapshotLineSchema).optional().nullable(),
    rate_subtotal: z.union([z.number(), z.string()]).optional().nullable(),
    nightly_rate: z.union([z.number(), z.string()]).optional().nullable(),
    nights: z.union([z.number(), z.string()]).optional().nullable(),
    extras: z.array(pricingSnapshotLineSchema).optional().nullable(),
    extras_total: z.union([z.number(), z.string()]).optional().nullable(),
    fees: z.union([z.number(), z.string()]).optional().nullable(),
    adjustments: z.union([z.number(), z.string()]).optional().nullable(),
    discount: z.union([z.number(), z.string()]).optional().nullable(),
    commission: z.union([z.number(), z.string()]).optional().nullable(),
    tax: z.union([z.number(), z.string()]).optional().nullable(),
    taxes: z.union([z.number(), z.string()]).optional().nullable(),
    deposit: z.union([z.number(), z.string()]).optional().nullable(),
    deposit_percent: z.union([z.number(), z.string()]).optional().nullable(),
    balance: z.union([z.number(), z.string()]).optional().nullable(),
    security: z.union([z.number(), z.string()]).optional().nullable(),
    security_deposit: z.union([z.number(), z.string()]).optional().nullable(),
    total: z.union([z.number(), z.string()]).optional().nullable(),
    grand_total: z.union([z.number(), z.string()]).optional().nullable(),
  })
  .passthrough();
export type PricingSnapshot = z.infer<typeof pricingSnapshotSchema>;

export const bookingOwnerSchema = z
  .object({
    id: z.number(),
    first_name: z.string(),
    last_name: z.string(),
    company: z.string(),
    primary_email: z.string().nullable(),
    primary_phone: z.string().nullable(),
    address_line_1: z.string(),
    address_line_2: z.string(),
  })
  .nullable();
export type BookingOwner = z.infer<typeof bookingOwnerSchema>;

export const bookingCommissionCalcTypeSchema = z.enum(["percent", "fixed"]);
export type BookingCommissionCalcType = z.infer<typeof bookingCommissionCalcTypeSchema>;

export const bookingCommissionSchema = z
  .object({
    calculation_type: bookingCommissionCalcTypeSchema.nullable(),
    amount: z.string().nullable(),
    note: z.string(),
  })
  .nullable();
export type BookingCommission = z.infer<typeof bookingCommissionSchema>;

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
  owner: bookingOwnerSchema.optional(),
  commission: bookingCommissionSchema.optional(),
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

// The backend activity endpoint returns a plain array (not paginated).
export const bookingActivityResponseSchema = z.array(bookingEventSchema);

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
  body: z.string().trim().min(1, i18n.t("bookings:schema_errors.body_required")).max(10_000),
  is_pinned: z.boolean(),
});
export type BookingNoteWriteInput = z.infer<typeof bookingNoteWriteInputSchema>;

// Enum label resolvers — resolve at call time so language switches take effect.
// Template-string keys are fine here: the fragment is a typed enum value.
export function bookingStatusLabel(status: BookingStatus): string {
  return i18n.t(`bookings:labels.status.${status}`);
}

export function bookingNoteKindLabel(kind: BookingNoteKind): string {
  return i18n.t(`bookings:labels.note_kind.${kind}`);
}

export function bookingNoteVisibilityLabel(visibility: BookingNoteVisibility): string {
  return i18n.t(`bookings:labels.note_visibility.${visibility}`);
}

export const bookingNoteKindOptions = (): Array<{ value: BookingNoteKind; label: string }> =>
  bookingNoteKindSchema.options.map((value) => ({ value, label: bookingNoteKindLabel(value) }));

export const bookingNoteVisibilityOptions = (): Array<{
  value: BookingNoteVisibility;
  label: string;
}> =>
  bookingNoteVisibilitySchema.options.map((value) => ({
    value,
    label: bookingNoteVisibilityLabel(value),
  }));

export const cancelBookingInputSchema = z.object({
  reason: z.string().trim().max(500, i18n.t("bookings:schema_errors.reason_max")).optional(),
});
export type CancelBookingInput = z.infer<typeof cancelBookingInputSchema>;

export const declineBookingInputSchema = z.object({
  reason: z
    .string()
    .trim()
    .min(1, i18n.t("bookings:schema_errors.reason_required"))
    .max(500, i18n.t("bookings:schema_errors.reason_max")),
});
export type DeclineBookingInput = z.infer<typeof declineBookingInputSchema>;

export const modifyDatesInputSchema = z
  .object({
    date_from: z.string().min(1, i18n.t("common:errors.field_required")),
    date_to: z.string().min(1, i18n.t("common:errors.field_required")),
    reason: z.string().trim().max(500, i18n.t("bookings:schema_errors.reason_max")).optional(),
  })
  .refine((v) => v.date_to > v.date_from, {
    message: i18n.t("bookings:schema_errors.check_out_after_check_in"),
    path: ["date_to"],
  });
export type ModifyDatesInput = z.infer<typeof modifyDatesInputSchema>;

export const modifyGuestsInputSchema = z.object({
  adults: z.number().int().min(1, i18n.t("bookings:schema_errors.at_least_one_adult")),
  children: z.number().int().min(0, i18n.t("bookings:schema_errors.children_negative")).optional(),
  reason: z.string().trim().max(500, i18n.t("bookings:schema_errors.reason_max")).optional(),
});
export type ModifyGuestsInput = z.infer<typeof modifyGuestsInputSchema>;

export const conciergeStatusSchema = z.enum(["requested", "confirmed", "cancelled", "delivered"]);
export type ConciergeStatus = z.infer<typeof conciergeStatusSchema>;

export const conciergeTierSchema = z.enum(["quintessential", "signature"]);
export type ConciergeTier = z.infer<typeof conciergeTierSchema>;

export const conciergeUnitSchema = z.enum(["day", "stay", "event", "hour"]);
export type ConciergeUnit = z.infer<typeof conciergeUnitSchema>;

export const bookingConciergeItemSchema = z.object({
  id: z.number(),
  booking: z.number().optional(),
  tier: conciergeTierSchema,
  name: z.string(),
  description: z.string().optional().default(""),
  quantity: z.number(),
  unit: conciergeUnitSchema,
  unit_price: z.string(),
  currency: z.number(),
  status: conciergeStatusSchema,
  notes: z.string().optional().default(""),
  created_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
});
export type BookingConciergeItem = z.infer<typeof bookingConciergeItemSchema>;

export const bookingConciergeItemsResponseSchema = paginated(bookingConciergeItemSchema);

export const conciergeItemWriteInputSchema = z.object({
  tier: conciergeTierSchema,
  name: z.string().trim().min(1, i18n.t("bookings:schema_errors.name_required")).max(200),
  description: z.string().trim().max(2000),
  quantity: z.number().int().min(1, i18n.t("bookings:schema_errors.quantity_min")),
  unit: conciergeUnitSchema,
  unit_price: z
    .string()
    .trim()
    .regex(/^\d+(\.\d{1,2})?$/, i18n.t("bookings:schema_errors.decimal_format")),
  currency: z.number().int(),
  notes: z.string().trim().max(2000),
});
export type ConciergeItemWriteInput = z.infer<typeof conciergeItemWriteInputSchema>;

export function conciergeStatusLabel(status: ConciergeStatus): string {
  return i18n.t(`bookings:labels.concierge_status.${status}`);
}

export function conciergeTierLabel(tier: ConciergeTier): string {
  return i18n.t(`bookings:labels.concierge_tier.${tier}`);
}

export function conciergeUnitLabel(unit: ConciergeUnit): string {
  return i18n.t(`bookings:labels.concierge_unit.${unit}`);
}

export const conciergeTierOptions = (): Array<{ value: ConciergeTier; label: string }> =>
  conciergeTierSchema.options.map((value) => ({ value, label: conciergeTierLabel(value) }));

export const conciergeUnitOptions = (): Array<{ value: ConciergeUnit; label: string }> =>
  conciergeUnitSchema.options.map((value) => ({ value, label: conciergeUnitLabel(value) }));

// ----------------------------------------------------------------------
// Payment tracks (deposit / balance / security)
// ----------------------------------------------------------------------

export const paymentTrackStatusSchema = z.enum([
  "pending",
  "processing",
  "succeeded",
  "failed",
  "refunded",
  "cancelled",
  "expired",
  "waived",
  "none",
]);
export type PaymentTrackStatus = z.infer<typeof paymentTrackStatusSchema>;

export const paymentPurposeSchema = z.enum([
  "deposit",
  "balance",
  "security_deposit",
  "concierge",
  "refund",
  "adjustment",
]);
export type PaymentPurpose = z.infer<typeof paymentPurposeSchema>;

export const paymentTrackSchema = z.object({
  booking: z.number(),
  purpose: paymentPurposeSchema,
  scheduled_amount: z.string(),
  paid_amount: z.string(),
  due_at: z.string().nullable(),
  status: paymentTrackStatusSchema,
});
export type PaymentTrack = z.infer<typeof paymentTrackSchema>;

export const paymentRecordSchema = z.object({
  id: z.number(),
  reference: z.string().nullable().optional(),
  booking: z.number(),
  purpose: paymentPurposeSchema,
  status: paymentTrackStatusSchema,
  amount: z.string(),
  currency: z.number(),
  provider: z.string().nullable().optional(),
  provider_reference: z.string().nullable().optional(),
  payment_method: z.string().nullable().optional(),
  due_at: z.string().nullable().optional(),
  requested_at: z.string().nullable().optional(),
  settled_at: z.string().nullable().optional(),
  failure_reason: z.string().nullable().optional(),
  meta: z.record(z.string(), z.unknown()).optional().default({}),
  concierge_item: z.number().nullable().optional(),
  created_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
});
export type PaymentRecord = z.infer<typeof paymentRecordSchema>;

export const paymentRecordsListSchema = z.array(paymentRecordSchema);

export function paymentTrackStatusLabel(status: PaymentTrackStatus): string {
  return i18n.t(`bookings:labels.payment_track_status.${status}`);
}

export const paymentMethodSchema = z.enum(["card", "bank_transfer", "other"]);
export type PaymentMethod = z.infer<typeof paymentMethodSchema>;

export function paymentMethodLabel(method: PaymentMethod): string {
  return i18n.t(`bookings:labels.payment_method.${method}`);
}

export const paymentMethodOptions = (): Array<{ value: PaymentMethod; label: string }> =>
  paymentMethodSchema.options.map((value) => ({ value, label: paymentMethodLabel(value) }));

export const markPaidInputSchema = z.object({
  amount: z
    .string()
    .trim()
    .regex(/^\d+(\.\d{1,2})?$/, i18n.t("bookings:schema_errors.decimal_amount_format")),
  paid_at: z.string().min(1, i18n.t("common:errors.field_required")),
  method: paymentMethodSchema,
  reference: z.string().trim().max(120),
  notes: z.string().trim().max(500),
});
export type MarkPaidInput = z.infer<typeof markPaidInputSchema>;

export const waiveTrackInputSchema = z.object({
  reason: z.string().trim().max(500),
});
export type WaiveTrackInput = z.infer<typeof waiveTrackInputSchema>;

export interface BookingFilters {
  q?: string;
  status?: BookingStatus;
  site?: string;
  ordering?: string;
  page?: number;
  check_in_after?: string;
  check_in_before?: string;
  check_out_after?: string;
  check_out_before?: string;
  exclude_terminal?: boolean;
}

export const bookingStatusOptions = (): Array<{ value: BookingStatus; label: string }> =>
  bookingStatusSchema.options.map((value) => ({ value, label: bookingStatusLabel(value) }));

// ----------------------------------------------------------------------
// Email logs (booking Comms tab) — surfaced by /bookings/{id}/emails.
// ----------------------------------------------------------------------

export const emailLogStatusSchema = z.enum(["queued", "sent", "failed", "bounced"]);
export type EmailLogStatus = z.infer<typeof emailLogStatusSchema>;

export function emailLogStatusLabel(status: EmailLogStatus): string {
  return i18n.t(`bookings:comms.status.${status}`);
}

export const bookingEmailSchema = z.object({
  id: z.number(),
  template_key: z.string(),
  template_version: z.number(),
  to: z.array(z.string()).optional().default([]),
  cc: z.array(z.string()).optional().default([]),
  bcc: z.array(z.string()).optional().default([]),
  from_email: z.string().nullable().optional(),
  subject: z.string().nullable().optional(),
  status: emailLogStatusSchema,
  queued_at: z.string().nullable().optional(),
  sent_at: z.string().nullable().optional(),
  failure_reason: z.string().optional().default(""),
  sender_user_id: z.number().nullable().optional(),
  smtp_profile_id: z.number().nullable().optional(),
  provider_reference: z.string().optional().default(""),
  correlation: z.record(z.string(), z.unknown()).optional().default({}),
});
export type BookingEmail = z.infer<typeof bookingEmailSchema>;

export const bookingEmailsResponseSchema = paginated(bookingEmailSchema);
