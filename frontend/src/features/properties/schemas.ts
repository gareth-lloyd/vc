import { z } from "zod";
import i18n from "@/i18n";
import { paginated } from "@/lib/api/pagination";

/**
 * Allowed contact-assignment roles. Mirrors the backend `accounts.ContactRole`
 * enum (`django_res/accounts/enums.py`); the model field is NOT NULL with these
 * choices, so the role is required and constrained to exactly these values.
 */
export const PROPERTY_CONTACT_ROLES = [
  "owner",
  "manager",
  "agent",
  "housekeeper",
  "owners_rep",
] as const;

export const propertyContactRoleSchema = z.enum(PROPERTY_CONTACT_ROLES, {
  error: () => i18n.t("properties:people.assignment_dialog.role_required"),
});
export type PropertyContactRole = z.infer<typeof propertyContactRoleSchema>;

// Read-only capacity block carried on list rows. `null` when the property has
// no `PropertyCapacity` row — distinct from a row whose `guests` is 0. The
// quote builder uses this to explain why a name-matched property is hidden.
export const propertyListCapacitySchema = z.object({
  guests: z.number(),
  additional_guests: z.number(),
  bedrooms: z.number(),
  ensuites: z.number(),
  bathrooms: z.number(),
  // String to match the dedicated capacity endpoint (DRF DecimalField); null
  // when unset.
  size_sqm: z.string().nullable().optional(),
});
export type PropertyListCapacity = z.infer<typeof propertyListCapacitySchema>;

/**
 * A property is hidden from quote searches when it has no capacity row or its
 * guest count is zero. This mirrors the backend `min_guests` filter
 * (`capacity__guests__gte`) and is the single source of that rule on the
 * frontend — used both for the quote-builder hint and the editor warning.
 */
export function isCapacityUnset(capacity: { guests: number } | null | undefined): boolean {
  return capacity == null || capacity.guests === 0;
}

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
  capacity: propertyListCapacitySchema.nullable().optional(),
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

export const DESCRIPTION_SECTIONS = [
  "overview",
  "house_rules",
  "villa_info",
  "further_info",
] as const;
export type DescriptionSection = (typeof DESCRIPTION_SECTIONS)[number];

export function sectionToSlug(section: DescriptionSection): string {
  return section.replace(/_/g, "-");
}

export const propertyDescriptionSchema = z.object({
  id: z.number(),
  property: z.number(),
  section: z.enum(DESCRIPTION_SECTIONS),
  body: z.string(),
  updated_at: z.string().nullable().optional(),
});
export type PropertyDescription = z.infer<typeof propertyDescriptionSchema>;

export const propertyDescriptionsResponseSchema = paginated(propertyDescriptionSchema);

export {
  featureSchema as propertyFeatureSchema,
  featuresListResponseSchema as propertyFeaturesResponseSchema,
  featureCategoriesListResponseSchema,
  featureCategorySchema,
} from "@/features/admin/tags/schemas";
export type { Feature as PropertyFeature, FeatureCategory } from "@/features/admin/tags/schemas";

export const ROOM_PLACEMENTS = [
  "main_house",
  "guest_house",
  "pool_house",
  "annex",
  "other",
] as const;
export type RoomPlacement = (typeof ROOM_PLACEMENTS)[number];

export const roomBedsSchema = z.object({
  double: z.number().int().min(0),
  twin_double: z.number().int().min(0),
  twin: z.number().int().min(0),
  single: z.number().int().min(0),
  bunk: z.number().int().min(0),
  sofa: z.number().int().min(0),
  childrens: z.number().int().min(0),
});
export type RoomBeds = z.infer<typeof roomBedsSchema>;

export const propertyRoomSchema = z.object({
  id: z.number(),
  property: z.number(),
  name: z.string(),
  placement: z.enum(ROOM_PLACEMENTS),
  website_description: z.string().nullable().optional(),
  vc_notes: z.string().nullable().optional(),
  is_ensuite: z.boolean(),
  sort_order: z.number().int(),
  beds: roomBedsSchema.optional(),
});
export type PropertyRoom = z.infer<typeof propertyRoomSchema>;

export const propertyRoomsResponseSchema = paginated(propertyRoomSchema);

export const nearbyPlaceTypeSchema = z.object({
  id: z.number(),
  name: z.string(),
  icon: z.string().nullable().optional(),
});
export type NearbyPlaceType = z.infer<typeof nearbyPlaceTypeSchema>;

export const nearbyPlaceTypesResponseSchema = paginated(nearbyPlaceTypeSchema);

export const propertyNearbyPlaceSchema = z.object({
  id: z.number(),
  property: z.number(),
  place_type: z.number(),
  name: z.string(),
  distance_km: z.string(),
  notes: z.string().nullable().optional(),
  sort_order: z.number().int(),
});
export type PropertyNearbyPlace = z.infer<typeof propertyNearbyPlaceSchema>;

export const propertyNearbyPlacesResponseSchema = paginated(propertyNearbyPlaceSchema);

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

export const changeOverRuleSchema = z.object({
  id: z.number(),
  property: z.number(),
  weekday: z.enum(PROPERTY_CHANGEOVER_DAYS),
  effective_from: z.string(),
  effective_to: z.string(),
  notes: z.string().nullable().optional(),
});
export type ChangeOverRule = z.infer<typeof changeOverRuleSchema>;

export const changeOverRulesResponseSchema = paginated(changeOverRuleSchema);

export const changeOverRuleWriteInputSchema = z
  .object({
    weekday: z.enum(PROPERTY_CHANGEOVER_DAYS),
    effective_from: z.string().min(1, { message: "properties:errors.changeover_from_required" }),
    effective_to: z.string().min(1, { message: "properties:errors.changeover_to_required" }),
    notes: z.string().trim().optional(),
  })
  .refine((v) => v.effective_to >= v.effective_from, {
    path: ["effective_to"],
    message: "properties:errors.changeover_to_before_from",
  });
export type ChangeOverRuleWriteInput = z.infer<typeof changeOverRuleWriteInputSchema>;

export const propertyNearbyPlaceWriteInputSchema = z.object({
  place_type: z.number().int(),
  name: z.string().trim().min(1, { message: "properties:errors.nearby_name_required" }).max(255),
  distance_km: z
    .string()
    .trim()
    .min(1, { message: "properties:errors.nearby_distance_required" })
    .regex(/^\d+(\.\d{1,2})?$/, { message: "properties:errors.nearby_distance_invalid" }),
  notes: z.string().trim().optional(),
});
export type PropertyNearbyPlaceWriteInput = z.infer<typeof propertyNearbyPlaceWriteInputSchema>;

export const propertyRoomWriteInputSchema = z.object({
  name: z.string().trim().min(1, { message: "properties:errors.room_name_required" }).max(128),
  placement: z.enum(ROOM_PLACEMENTS),
  website_description: z.string().trim(),
  vc_notes: z.string().trim(),
  is_ensuite: z.boolean(),
  beds: roomBedsSchema,
});
export type PropertyRoomWriteInput = z.infer<typeof propertyRoomWriteInputSchema>;

export interface PropertyFilters {
  q?: string;
  country?: string;
  status?: string;
  ordering?: string;
  page?: number;
}

export const PROPERTY_PRICE_BASES = ["gross", "net"] as const;

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
  sort_order: z.number().nullable().optional(),
  is_active: z.boolean().optional(),
  notes: z.string().nullable().optional(),
  rules: z.array(rateRuleSchema).optional().default([]),
});
export type RateCard = z.infer<typeof rateCardSchema>;

export const rateCardWriteInputSchema = z
  .object({
    name: z
      .string()
      .trim()
      .min(1, { message: "properties:errors.rate_card_name_required" })
      .max(128),
    description: z.string().trim().optional(),
    min_nights: z
      .number({ message: "properties:errors.rate_card_min_nights_required" })
      .int()
      .min(1, { message: "properties:errors.rate_card_min_nights_required" }),
    max_nights: z.number().int().min(1).nullable().optional(),
    is_active: z.boolean().optional(),
    notes: z.string().trim().optional(),
  })
  .refine((v) => v.max_nights == null || v.max_nights >= v.min_nights, {
    path: ["max_nights"],
    message: "properties:errors.rate_card_max_nights_lt_min",
  });
export type RateCardWriteInput = z.infer<typeof rateCardWriteInputSchema>;

const MONEY_PATTERN = /^\d{1,10}(\.\d{1,2})?$/;

export const rateRuleWriteInputSchema = z
  .object({
    date_from: z.string().min(1, { message: "properties:errors.rule_date_from_required" }),
    date_to: z.string().min(1, { message: "properties:errors.rule_date_to_required" }),
    min_party: z
      .number({ message: "properties:errors.rule_min_party_required" })
      .int()
      .min(1, { message: "properties:errors.rule_min_party_required" }),
    max_party: z
      .number({ message: "properties:errors.rule_max_party_required" })
      .int()
      .min(1, { message: "properties:errors.rule_max_party_required" }),
    nightly: z.string().trim().optional(),
    weekly: z.string().trim().optional(),
    is_poa: z.boolean(),
    notes: z.string().trim().optional(),
  })
  // DB constraint is strict (`date_from < date_to`), unlike seasons' `>=`.
  .refine((v) => !v.date_from || !v.date_to || v.date_to > v.date_from, {
    path: ["date_to"],
    message: "properties:errors.rule_date_to_not_after_from",
  })
  .refine((v) => v.max_party >= v.min_party, {
    path: ["max_party"],
    message: "properties:errors.rule_max_party_lt_min",
  })
  // Prices only matter when the rule isn't POA — the submit payload nulls
  // them under POA, so leftovers in the disabled inputs must not block a save.
  .superRefine((v, ctx) => {
    if (v.is_poa) return;
    for (const key of ["nightly", "weekly"] as const) {
      const value = v[key];
      if (value && !MONEY_PATTERN.test(value)) {
        ctx.addIssue({
          code: "custom",
          path: [key],
          message: "properties:errors.rule_price_invalid",
        });
      }
    }
    if (!v.nightly && !v.weekly) {
      ctx.addIssue({
        code: "custom",
        path: ["nightly"],
        message: "properties:errors.rule_price_required",
      });
    }
  });
export type RateRuleWriteInput = z.infer<typeof rateRuleWriteInputSchema>;

/** Wire shape: empty/POA-masked money fields are sent as explicit nulls. */
export type RateRuleWritePayload = Omit<RateRuleWriteInput, "nightly" | "weekly"> & {
  nightly: string | null;
  weekly: string | null;
};

export const ratePlanSchema = z.object({
  id: z.number(),
  property: z.number(),
  name: z.string(),
  currency: z.number().nullable().optional(),
  currency_code: z.string().nullable().optional(),
  price_basis: z.enum(PROPERTY_PRICE_BASES).nullable().optional(),
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
  currency: z.number().nullable().optional(),
  currency_code: z.string().nullable().optional(),
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
  notes: z.string().nullable().optional(),
  created_at: z.string().nullable().optional(),
});
export type AvailabilityHold = z.infer<typeof availabilityHoldSchema>;

export const availabilityHoldsResponseSchema = z.object({
  records: z.array(availabilityHoldSchema),
});

export const availabilityCellSegmentSchema = z.object({
  available: z.boolean(),
  reason: z.string(),
  block_id: z.number().nullable().optional(),
});
export type AvailabilityCellSegment = z.infer<typeof availabilityCellSegmentSchema>;

export const availabilityCellSchema = z.object({
  date: z.string(),
  available: z.boolean(),
  reason: z.string(),
  block_id: z.number().nullable().optional(),
  segments: z
    .object({ am: availabilityCellSegmentSchema, pm: availabilityCellSegmentSchema })
    .nullable()
    .optional(),
});
export type AvailabilityCell = z.infer<typeof availabilityCellSchema>;

export const availabilityCalendarResponseSchema = z.object({
  property_id: z.number(),
  cells: z.array(availabilityCellSchema),
});
export type AvailabilityCalendarResponse = z.infer<typeof availabilityCalendarResponseSchema>;

export const AVAILABILITY_BLOCK_REASONS = ["owner_block", "maintenance", "manual"] as const;

export const availabilityBlockWriteInputSchema = z
  .object({
    reason: z.enum(AVAILABILITY_BLOCK_REASONS),
    date_from: z.string().min(1, { message: "properties:errors.block_from_required" }),
    date_to: z.string().min(1, { message: "properties:errors.block_to_required" }),
    notes: z.string().trim().optional(),
  })
  .refine((v) => v.date_to > v.date_from, {
    path: ["date_to"],
    message: "properties:errors.block_to_before_from",
  });
export type AvailabilityBlockWriteInput = z.infer<typeof availabilityBlockWriteInputSchema>;

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

export const ratePlanWriteInputSchema = z
  .object({
    name: z.string().trim().min(1, { message: "properties:errors.season_name_required" }).max(255),
    currency: z
      .number({ message: "properties:errors.season_currency_required" })
      .int()
      .min(1, { message: "properties:errors.season_currency_required" }),
    price_basis: z.enum(PROPERTY_PRICE_BASES),
    effective_from: z
      .string()
      .min(1, { message: "properties:errors.season_effective_from_required" }),
    effective_to: z.string().optional(),
    is_active: z.boolean().optional(),
    notes: z.string().trim().optional(),
    inclusion: z.string().trim().optional(),
  })
  .refine((v) => !v.effective_to || v.effective_to >= v.effective_from, {
    path: ["effective_to"],
    message: "properties:errors.season_effective_to_before_from",
  });
export type RatePlanWriteInput = z.infer<typeof ratePlanWriteInputSchema>;

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
  // IANA timezone, sourced from the property's location; null when the
  // property has no location row yet. Not inheritable from the group.
  timezone: z.string().nullable().optional(),
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
  // `timezone` is read-only on settings (surfaced for context in the response);
  // it is written via the property location endpoint, not here.
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

export const propertyLocationSchema = z.object({
  property: z.number(),
  address_line_1: z.string().nullable().optional(),
  address_line_2: z.string().nullable().optional(),
  address_line_3: z.string().nullable().optional(),
  post_code: z.string().nullable().optional(),
  locality_town: z.string().nullable().optional(),
  locality_region: z.string().nullable().optional(),
  // Non-nullable FK on the model; always present on read.
  country: z.number(),
  // Decimals are serialized as strings by DRF; null when unset.
  latitude: z.string().nullable().optional(),
  longitude: z.string().nullable().optional(),
  timezone: z.string(),
});
export type PropertyLocation = z.infer<typeof propertyLocationSchema>;

export const propertyLocationWriteInputSchema = z.object({
  address_line_1: z.string().nullable().optional(),
  address_line_2: z.string().nullable().optional(),
  address_line_3: z.string().nullable().optional(),
  post_code: z.string().nullable().optional(),
  locality_town: z.string().nullable().optional(),
  locality_region: z.string().nullable().optional(),
  country: z.number().int(),
  // Coordinate ranges are enforced by the backend (surfaced as inline field
  // errors); blank inputs are sent as null to clear the value.
  latitude: z.string().nullable().optional(),
  longitude: z.string().nullable().optional(),
  timezone: z.string(),
});
export type PropertyLocationWriteInput = z.infer<typeof propertyLocationWriteInputSchema>;

export const propertyCapacitySchema = z.object({
  property: z.number(),
  guests: z.number(),
  additional_guests: z.number(),
  bedrooms: z.number(),
  ensuites: z.number(),
  bathrooms: z.number(),
  // DRF serialises the DecimalField as a string; null when unset.
  size_sqm: z.string().nullable().optional(),
});
export type PropertyCapacity = z.infer<typeof propertyCapacitySchema>;

export const propertyCapacityWriteInputSchema = z.object({
  guests: z.number().int().min(0),
  additional_guests: z.number().int().min(0),
  bedrooms: z.number().int().min(0),
  ensuites: z.number().int().min(0),
  bathrooms: z.number().int().min(0),
  // Free-floor area in m²; blank normalises to null in the api layer.
  size_sqm: z.string().nullable().optional(),
});
export type PropertyCapacityWriteInput = z.infer<typeof propertyCapacityWriteInputSchema>;

export const propertyContactAssignmentWriteInputSchema = z.object({
  contact: z.number().int(),
  role: propertyContactRoleSchema,
  start_date: z.string().optional(),
  end_date: z.string().optional(),
  is_primary: z.boolean().optional(),
});
export type PropertyContactAssignmentWriteInput = z.infer<
  typeof propertyContactAssignmentWriteInputSchema
>;
