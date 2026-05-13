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

export const contactEmailSchema = z.object({
  id: z.number(),
  email: z.string(),
  label: z.string().nullable().optional(),
  is_primary: z.boolean().optional(),
});
export type ContactEmail = z.infer<typeof contactEmailSchema>;

export const contactPhoneSchema = z.object({
  id: z.number(),
  number: z.string(),
  label: z.string().nullable().optional(),
  is_primary: z.boolean().optional(),
});
export type ContactPhone = z.infer<typeof contactPhoneSchema>;

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

export const contactEmailWriteInputSchema = z.object({
  email: z.string().email("Enter a valid email").max(254),
  label: z.string().trim().max(40).optional(),
  is_primary: z.boolean().optional(),
});
export type ContactEmailWriteInput = z.infer<typeof contactEmailWriteInputSchema>;

export const contactPhoneWriteInputSchema = z.object({
  number: z.string().trim().min(1, "Required").max(40),
  label: z.string().trim().max(40).optional(),
  is_primary: z.boolean().optional(),
});
export type ContactPhoneWriteInput = z.infer<typeof contactPhoneWriteInputSchema>;

export const contactWriteInputSchema = z
  .object({
    title: z.string().trim().max(40).optional(),
    first_name: z.string().trim().max(80).optional(),
    last_name: z.string().trim().max(80).optional(),
    company: z.string().trim().max(160).optional(),
    website_url: z.string().trim().max(255).optional(),
    preferred_method: z.string().trim().max(40).optional(),
    address_line_1: z.string().trim().max(255).optional(),
    address_line_2: z.string().trim().max(255).optional(),
    notes: z.string().trim().max(2000).optional(),
  })
  .refine((v) => v.first_name || v.last_name || v.company, {
    message: "At least a name or company is required",
    path: ["first_name"],
  });
export type ContactWriteInput = z.infer<typeof contactWriteInputSchema>;

export const contactSchema = z.object({
  id: z.number(),
  title: z.string().nullable().optional(),
  first_name: z.string().nullable().optional(),
  last_name: z.string().nullable().optional(),
  company: z.string().nullable().optional(),
  website_url: z.string().nullable().optional(),
  preferred_method: z.string().nullable().optional(),
  address_line_1: z.string().nullable().optional(),
  address_line_2: z.string().nullable().optional(),
  notes: z.string().nullable().optional(),
  status: z.string().nullable().optional(),
  emails: z.array(contactEmailSchema).optional().default([]),
  phones: z.array(contactPhoneSchema).optional().default([]),
});
export type Contact = z.infer<typeof contactSchema>;
