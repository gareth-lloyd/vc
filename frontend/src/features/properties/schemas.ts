import { z } from "zod";
import { paginated } from "@/lib/api/pagination";

export const propertyListItemSchema = z.object({
  id: z.number(),
  name: z.string(),
  display_name: z.string().nullable().optional(),
  slug: z.string().nullable().optional(),
  licence_number: z.string().nullable().optional(),
  status: z.string(),
  channel: z.string().nullable().optional(),
  category: z.number().nullable().optional(),
  group: z.number().nullable().optional(),
  region: z.number().nullable().optional(),
  created_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
});
export type PropertyListItem = z.infer<typeof propertyListItemSchema>;

export const propertyDetailSchema = propertyListItemSchema.extend({
  feature_ids: z.array(z.number()).optional().default([]),
  legacy_id: z.union([z.string(), z.number()]).nullable().optional(),
});
export type PropertyDetail = z.infer<typeof propertyDetailSchema>;

export const propertyListResponseSchema = paginated(propertyListItemSchema);

export const propertyDescriptionSchema = z.object({
  id: z.number(),
  title: z.string().nullable().optional(),
  body_html: z.string().nullable().optional(),
  body: z.string().nullable().optional(),
  language: z.string().nullable().optional(),
});
export type PropertyDescription = z.infer<typeof propertyDescriptionSchema>;

export const propertyDescriptionsResponseSchema = paginated(propertyDescriptionSchema);

export const propertyFeatureSchema = z.object({
  id: z.number(),
  name: z.string().optional(),
  slug: z.string().optional(),
});
export type PropertyFeature = z.infer<typeof propertyFeatureSchema>;

export const propertyFeaturesResponseSchema = paginated(propertyFeatureSchema);

export const propertyRoomSchema = z.object({
  id: z.number(),
  name: z.string().optional(),
  kind: z.string().nullable().optional(),
  count: z.number().nullable().optional(),
});
export type PropertyRoom = z.infer<typeof propertyRoomSchema>;

export const propertyRoomsResponseSchema = paginated(propertyRoomSchema);

export interface PropertyFilters {
  q?: string;
  country?: string;
  status?: string;
  ordering?: string;
  page?: number;
}

export const rateRuleSchema = z.object({
  id: z.number(),
  card: z.number(),
  date_from: z.string(),
  date_to: z.string(),
  min_party: z.number().nullable().optional(),
  max_party: z.number().nullable().optional(),
  priority: z.number().nullable().optional(),
  nightly: z.string().nullable().optional(),
  weekly: z.string().nullable().optional(),
  is_poa: z.boolean().optional(),
  is_locked: z.boolean().optional(),
  is_approved: z.boolean().optional(),
  notes: z.string().nullable().optional(),
});
export type RateRule = z.infer<typeof rateRuleSchema>;

export const rateCardSchema = z.object({
  id: z.number(),
  plan: z.number(),
  name: z.string(),
  description: z.string().nullable().optional(),
  min_nights: z.number().nullable().optional(),
  max_nights: z.number().nullable().optional(),
  changeover_weekday: z.number().nullable().optional(),
  sort_order: z.number().nullable().optional(),
  is_active: z.boolean().optional(),
  notes: z.string().nullable().optional(),
  rules: z.array(rateRuleSchema).optional().default([]),
});
export type RateCard = z.infer<typeof rateCardSchema>;

export const ratePlanSchema = z.object({
  id: z.number(),
  property: z.number(),
  name: z.string(),
  currency: z.string().nullable().optional(),
  price_basis: z.string().nullable().optional(),
  effective_from: z.string().nullable().optional(),
  effective_to: z.string().nullable().optional(),
  is_active: z.boolean().optional(),
  notes: z.string().nullable().optional(),
  inclusion: z.string().nullable().optional(),
});
export type RatePlan = z.infer<typeof ratePlanSchema>;

export const ratePlanDetailSchema = ratePlanSchema.extend({
  cards: z.array(rateCardSchema).optional().default([]),
});
export type RatePlanDetail = z.infer<typeof ratePlanDetailSchema>;

export const ratePlansResponseSchema = paginated(ratePlanSchema);

export const extraSchema = z.object({
  id: z.number(),
  property: z.number(),
  name: z.string(),
  description: z.string().nullable().optional(),
  kind: z.string().nullable().optional(),
  calc: z.string().nullable().optional(),
  amount: z.string().nullable().optional(),
  currency: z.string().nullable().optional(),
  is_mandatory: z.boolean().optional(),
  applies_from: z.string().nullable().optional(),
  applies_to: z.string().nullable().optional(),
  min_party: z.number().nullable().optional(),
  max_party: z.number().nullable().optional(),
  sort_order: z.number().nullable().optional(),
  is_active: z.boolean().optional(),
  notes: z.string().nullable().optional(),
});
export type Extra = z.infer<typeof extraSchema>;

export const extrasResponseSchema = paginated(extraSchema);

export const discountSchema = z.object({
  id: z.number(),
  card: z.number().nullable().optional(),
  property: z.number().nullable().optional(),
  name: z.string(),
  code: z.string().nullable().optional(),
  rule_kind: z.string().nullable().optional(),
  kind: z.string().nullable().optional(),
  amount: z.string().nullable().optional(),
  min_nights: z.number().nullable().optional(),
  threshold_days: z.number().nullable().optional(),
  valid_from: z.string().nullable().optional(),
  valid_to: z.string().nullable().optional(),
  max_uses: z.number().nullable().optional(),
  uses_count: z.number().nullable().optional(),
  is_active: z.boolean().optional(),
});
export type Discount = z.infer<typeof discountSchema>;

export const discountsResponseSchema = paginated(discountSchema);

export const propertyContactAssignmentSchema = z.object({
  id: z.number(),
  property: z.number(),
  contact: z.number(),
  role: z.string().nullable().optional(),
  start_date: z.string().nullable().optional(),
  end_date: z.string().nullable().optional(),
  is_primary: z.boolean().optional(),
});
export type PropertyContactAssignment = z.infer<typeof propertyContactAssignmentSchema>;

export const propertyContactsResponseSchema = paginated(propertyContactAssignmentSchema);

export const availabilityHoldSchema = z.object({
  id: z.number(),
  property: z.number(),
  date_from: z.string(),
  date_to: z.string(),
  expires_at: z.string().nullable().optional(),
  released_at: z.string().nullable().optional(),
  reason: z.string(),
  created_at: z.string().nullable().optional(),
});
export type AvailabilityHold = z.infer<typeof availabilityHoldSchema>;

export const availabilityHoldsResponseSchema = z.object({
  records: z.array(availabilityHoldSchema),
});

export const propertyBookingItemSchema = z.object({
  id: z.number(),
  reference: z.string(),
  status: z.string(),
  date_from: z.string(),
  date_to: z.string(),
  guest_name: z.string().nullable().optional(),
});
export type PropertyBookingItem = z.infer<typeof propertyBookingItemSchema>;

export const propertyBookingsResponseSchema = paginated(propertyBookingItemSchema);

export const PROPERTY_IMAGE_KINDS = [
  "hero",
  "interior",
  "exterior",
  "gallery",
  "floor_plan",
] as const;
export type PropertyImageKind = (typeof PROPERTY_IMAGE_KINDS)[number];

export const PROPERTY_IMAGE_KIND_LABELS: Record<PropertyImageKind, string> = {
  hero: "Hero",
  interior: "Interior",
  exterior: "Exterior",
  gallery: "Gallery",
  floor_plan: "Floor plan",
};

export const propertyImageSchema = z.object({
  id: z.number(),
  property: z.number(),
  image: z.string().nullable().optional(),
  kind: z.string(),
  name: z.string().nullable().optional(),
  description: z.string().nullable().optional(),
  sort_order: z.number().nullable().optional(),
  is_active: z.boolean().optional(),
  created_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
});
export type PropertyImage = z.infer<typeof propertyImageSchema>;

export const propertyImagesResponseSchema = paginated(propertyImageSchema);

export const propertyImageWriteInputSchema = z.object({
  key: z.string().trim().min(1, { message: "properties:errors.image_key_required" }).max(512),
  kind: z.enum(PROPERTY_IMAGE_KINDS),
  name: z.string().trim().max(255).optional(),
  description: z.string().trim().optional(),
  sort_order: z.number().int().min(0).optional(),
  is_active: z.boolean().optional(),
});
export type PropertyImageWriteInput = z.infer<typeof propertyImageWriteInputSchema>;

export const PROPERTY_AVAILABILITY_DEFAULTS = ["available", "unavailable", "on_request"] as const;
export const PROPERTY_CHANGEOVER_DAYS = [
  "mon",
  "tue",
  "wed",
  "thu",
  "fri",
  "sat",
  "sun",
  "any",
] as const;
export const PROPERTY_PRICE_BASES = ["gross", "net"] as const;

export const propertySettingsSchema = z.object({
  property: z.number(),
  availability_default: z.string().nullable().optional(),
  bookings_require_pre_approval: z.boolean().nullable().optional(),
  requires_enquiry_first: z.boolean().nullable().optional(),
  currency: z.number().nullable().optional(),
  check_in_time: z.string().nullable().optional(),
  check_out_time: z.string().nullable().optional(),
  changeover_day: z.string().nullable().optional(),
  min_nights_rental: z.number().nullable().optional(),
  min_nights_rental_note: z.string().nullable().optional(),
  prices_entered_as: z.string().nullable().optional(),
});
export type PropertySettings = z.infer<typeof propertySettingsSchema>;

export const propertySettingsWriteInputSchema = z.object({
  availability_default: z.string().nullable().optional(),
  bookings_require_pre_approval: z.boolean().nullable().optional(),
  requires_enquiry_first: z.boolean().nullable().optional(),
  currency: z.number().nullable().optional(),
  check_in_time: z.string().nullable().optional(),
  check_out_time: z.string().nullable().optional(),
  changeover_day: z.string().nullable().optional(),
  min_nights_rental: z.number().int().min(0).nullable().optional(),
  min_nights_rental_note: z.string().nullable().optional(),
  prices_entered_as: z.string().nullable().optional(),
});
export type PropertySettingsWriteInput = z.infer<typeof propertySettingsWriteInputSchema>;

export const propertyFinanceSchema = z.object({
  property: z.number(),
  commission_calculation_type: z.string().nullable().optional(),
  commission_amount: z.string().nullable().optional(),
  commission_note: z.string().nullable().optional(),
  tax_number: z.string().nullable().optional(),
  tax_is_exempt: z.boolean().nullable().optional(),
  tax_percentage: z.string().nullable().optional(),
  bank_account_name: z.string().nullable().optional(),
  bank_name: z.string().nullable().optional(),
  bank_address_line_1: z.string().nullable().optional(),
  bank_address_line_2: z.string().nullable().optional(),
  bank_post_code: z.string().nullable().optional(),
  bank_city: z.string().nullable().optional(),
  deposit_required: z.boolean().nullable().optional(),
  deposit_calculation_type: z.string().nullable().optional(),
  deposit_amount: z.string().nullable().optional(),
  interim_required: z.boolean().nullable().optional(),
  interim_calculation_type: z.string().nullable().optional(),
  interim_amount: z.string().nullable().optional(),
  days_interim_due_before_arrival: z.number().nullable().optional(),
  days_balance_due_before_arrival: z.number().nullable().optional(),
  security_deposit_required: z.boolean().nullable().optional(),
  security_deposit_calculation_type: z.string().nullable().optional(),
  security_deposit_amount: z.string().nullable().optional(),
  security_deposit_calculate_from: z.string().nullable().optional(),
  security_deposit_days_due_before_arrival: z.number().nullable().optional(),
  security_deposit_days_refunded_after_departure: z.number().nullable().optional(),
  security_deposit_payment_method: z.string().nullable().optional(),
  cancellation_fee_amount: z.string().nullable().optional(),
  cancellation_fee_percent: z.string().nullable().optional(),
  cancellation_window_days: z.number().nullable().optional(),
  cancellation_notes: z.string().nullable().optional(),
  notes: z.string().nullable().optional(),
  season: z.number().nullable().optional(),
  contact: z.number().nullable().optional(),
  parent: z.number().nullable().optional(),
});
export type PropertyFinance = z.infer<typeof propertyFinanceSchema>;

export const propertyFinanceWriteInputSchema = z.object({
  commission_calculation_type: z.string().nullable().optional(),
  commission_amount: z.string().nullable().optional(),
  commission_note: z.string().nullable().optional(),
  tax_number: z.string().nullable().optional(),
  tax_is_exempt: z.boolean().nullable().optional(),
  tax_percentage: z.string().nullable().optional(),
  deposit_required: z.boolean().nullable().optional(),
  deposit_calculation_type: z.string().nullable().optional(),
  deposit_amount: z.string().nullable().optional(),
  days_balance_due_before_arrival: z.number().int().min(0).nullable().optional(),
  security_deposit_required: z.boolean().nullable().optional(),
  security_deposit_calculation_type: z.string().nullable().optional(),
  security_deposit_amount: z.string().nullable().optional(),
  cancellation_fee_percent: z.string().nullable().optional(),
  cancellation_window_days: z.number().int().min(0).nullable().optional(),
  notes: z.string().nullable().optional(),
});
export type PropertyFinanceWriteInput = z.infer<typeof propertyFinanceWriteInputSchema>;

export const propertyContactAssignmentWriteInputSchema = z.object({
  contact: z.number().int(),
  role: z.string().trim().max(120).optional(),
  start_date: z.string().optional(),
  end_date: z.string().optional(),
  is_primary: z.boolean().optional(),
});
export type PropertyContactAssignmentWriteInput = z.infer<
  typeof propertyContactAssignmentWriteInputSchema
>;
