import { z } from "zod";
import i18n from "@/i18n";
import { paginated } from "@/lib/api/pagination";
import { PROPERTY_CONTACT_ROLES } from "@/lib/domain/contactRoles";
import {
  PROPERTY_AVAILABILITY_DEFAULTS,
  PROPERTY_CHANGEOVER_DAYS,
  PROPERTY_PRICE_BASES,
} from "@/lib/domain/propertyEnums";

// Re-exported for intra-feature use; the canonical list lives in lib/domain
// (GAP-072) so contacts can allowlist property roles without an edge back here.
export { PROPERTY_CONTACT_ROLES };
// Property-config enum tuples likewise live in lib/domain so the
// admin/property-defaults editor can consume them without a cross-feature edge.
export { PROPERTY_AVAILABILITY_DEFAULTS, PROPERTY_CHANGEOVER_DAYS, PROPERTY_PRICE_BASES };

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
  region: z.number().nullable().optional(),
  capacity: propertyListCapacitySchema.nullable().optional(),
  // Whether the row is free across the request's date_from..date_to window;
  // null when the request carried no date range (availability undefined).
  available_for_range: z.boolean().nullable().optional(),
  // GAP-034 calendar-source indicators. `has_active_ical_feed` defaults to false
  // so older fixtures that omit it still parse; `calendar_url` is the owner's
  // online (non-iCal) calendar webpage (null when unset). Precedence (badge wins
  // over link) is decided by `CalendarSourceIndicator`.
  has_active_ical_feed: z.boolean().optional().default(false),
  calendar_url: z.string().nullable().optional(),
  // GAP-033 availability-freshness signals, shown as three separate labelled
  // lines (never conflated): when an owner last changed availability (Signal 1),
  // when the iCal feed last polled (Signal 2, only meaningful with a feed), and
  // when VC staff last confirmed it current + who (Signal 3). All nullable —
  // a brand-new property has none yet.
  availability_owner_updated_at: z.string().nullable().optional(),
  availability_confirmed_at: z.string().nullable().optional(),
  availability_confirmed_by_name: z.string().nullable().optional(),
  calendar_last_imported_at: z.string().nullable().optional(),
  created_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
});
export type PropertyListItem = z.infer<typeof propertyListItemSchema>;

export const propertyDetailSchema = propertyListItemSchema.extend({
  feature_ids: z.array(z.number()).optional().default([]),
  hero_image_url: z.string().nullable().optional(),
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

// GAP-065: the building axis. Blank means "unknown / not specified" (the
// backend dropped the defaulted main_house lie). Tuple order doubles as the
// grouped rooms-list display order.
export const ROOM_PLACEMENTS = [
  "main_house",
  "guest_house",
  "pool_house",
  "annex",
  "cottage",
  "bungalow",
  "studio",
  "other",
] as const;
export type RoomPlacement = (typeof ROOM_PLACEMENTS)[number];
export const roomPlacementSchema = z.enum(ROOM_PLACEMENTS);

// GAP-065: the floor ladder, bottom→top; blank = unknown. Tuple order doubles
// as the grouped rooms-list display order within a building.
export const ROOM_FLOORS = ["lower_ground", "ground", "first", "second", "third_plus"] as const;
export type RoomFloor = (typeof ROOM_FLOORS)[number];
export const roomFloorSchema = z.enum(ROOM_FLOORS);

// GAP-064 room facets. Blank means "unknown / not specified" on both — the
// backend stores "" and a non-blank ensuite_type auto-refines `is_ensuite` to
// true server-side (mirrored in the form UI).
export const ENSUITE_TYPES = ["shower", "bath", "both"] as const;
export type EnsuiteType = (typeof ENSUITE_TYPES)[number];
export const ensuiteTypeSchema = z.enum(ENSUITE_TYPES);

export const ROOM_ACCESS = ["inside", "outside"] as const;
export type RoomAccess = (typeof ROOM_ACCESS)[number];
export const roomAccessSchema = z.enum(ROOM_ACCESS);

// GAP-066 bed size on the double count; blank = unspecified. Only meaningful
// when `double > 0` — the form gates visibility, the schema stays permissive.
export const ROOM_DOUBLE_SIZES = ["king", "super_king", "emperor"] as const;
export type RoomDoubleSize = (typeof ROOM_DOUBLE_SIZES)[number];
export const roomDoubleSizeSchema = z.enum(ROOM_DOUBLE_SIZES);

// GAP-064 amenity catalog row (`GET /room-attributes`). The endpoint serves
// INACTIVE rows too, so retired-but-assigned amenities can still be labelled.
export const roomAttributeSchema = z.object({
  id: z.number(),
  slug: z.string(),
  name: z.string(),
  description: z.string().nullable().optional(),
  icon: z.string().nullable().optional(),
  sort_order: z.number().int(),
  is_active: z.boolean(),
  implies_property_feature: z.number().nullable().optional(),
});
export type RoomAttribute = z.infer<typeof roomAttributeSchema>;

export const roomAttributesResponseSchema = paginated(roomAttributeSchema);

// Read shape of one room↔amenity link: the assignment row plus the catalog
// row's display fields (incl. `is_active` so the form can badge retired rows
// instead of silently dropping them on a full-list save).
export const roomAttributeLinkSchema = z.object({
  id: z.number(),
  attribute: z.number(),
  slug: z.string(),
  name: z.string(),
  icon: z.string().nullable().optional(),
  is_active: z.boolean(),
  note: z.string().optional().default(""),
});
export type RoomAttributeLink = z.infer<typeof roomAttributeLinkSchema>;

export const roomBedsSchema = z.object({
  double: z.number().int().min(0),
  // GAP-066 size of the double bed; blank = unspecified. `.optional()` (no
  // `.default`) so pre-GAP-066 beds fixtures still parse AND the input/output
  // types stay aligned for react-hook-form. The form always emits it (from
  // EMPTY_BEDS), so a PATCH can still send "" to clear a previously-set size.
  double_size: roomDoubleSizeSchema.or(z.literal("")).optional(),
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
  // GAP-065 location axes; blank = unknown. Defaulted so older fixtures parse.
  placement: roomPlacementSchema.or(z.literal("")).optional().default(""),
  floor: roomFloorSchema.or(z.literal("")).optional().default(""),
  // Read-only preserved legacy placement string (GAP-065). API-writable but
  // deliberately NOT in the write schema — the form only displays it.
  placement_note: z.string().optional().default(""),
  website_description: z.string().nullable().optional(),
  vc_notes: z.string().nullable().optional(),
  is_ensuite: z.boolean(),
  // GAP-064 facets; blank = unknown. Defaulted so older fixtures still parse.
  ensuite_type: ensuiteTypeSchema.or(z.literal("")).optional().default(""),
  access: roomAccessSchema.or(z.literal("")).optional().default(""),
  sort_order: z.number().int(),
  beds: roomBedsSchema.optional(),
  attribute_links: z.array(roomAttributeLinkSchema).optional().default([]),
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

// PropertyService (GAP-037): informational, date-ranged included services that
// replace the legacy free-text RatePlan.inclusion. `applies_from`/`applies_to`
// are absolute ISO dates; either being null means the band is open on that end
// (a null/null band is year-round).
export const propertyServiceSchema = z.object({
  id: z.number(),
  property: z.number(),
  name: z.string(),
  copy: z.string(),
  notes: z.string().nullable().optional(),
  applies_from: z.string().nullable().optional(),
  applies_to: z.string().nullable().optional(),
  sort_order: z.number().int(),
  is_active: z.boolean(),
});
export type PropertyService = z.infer<typeof propertyServiceSchema>;

export const propertyServicesResponseSchema = paginated(propertyServiceSchema);

export const propertyServiceWriteInputSchema = z
  .object({
    name: z.string().trim().min(1, { message: "properties:errors.service_name_required" }).max(128),
    copy: z.string().trim().min(1, { message: "properties:errors.service_copy_required" }),
    notes: z.string().trim().optional(),
    // Nullable so an emptied date input can be sent as explicit `null` to CLEAR
    // an existing band on PATCH (converting a banded service to year-round).
    // `.optional()` alone would emit `undefined`, omit the field, and silently
    // leave the old band in place — the same trap documented on
    // `propertyRoomWriteInputSchema` below.
    applies_from: z.string().nullable().optional(),
    applies_to: z.string().nullable().optional(),
    is_active: z.boolean().optional(),
  })
  .refine((v) => !v.applies_from || !v.applies_to || v.applies_to >= v.applies_from, {
    path: ["applies_to"],
    message: "properties:errors.service_to_before_from",
  });
export type PropertyServiceWriteInput = z.infer<typeof propertyServiceWriteInputSchema>;

export const propertyRoomWriteInputSchema = z.object({
  name: z.string().trim().min(1, { message: "properties:errors.room_name_required" }).max(128),
  // GAP-065 location axes + GAP-064 facets: blank-able enums, NOT `.optional()`
  // — PATCH must be able to send `""` to clear a previously-set value (same
  // clearing trap as `website_description`/`vc_notes` below). `placement_note`
  // is deliberately absent: the form never writes it (absent on PATCH ⇒
  // untouched server-side).
  placement: roomPlacementSchema.or(z.literal("")),
  floor: roomFloorSchema.or(z.literal("")),
  website_description: z.string().trim(),
  vc_notes: z.string().trim(),
  is_ensuite: z.boolean(),
  ensuite_type: ensuiteTypeSchema.or(z.literal("")),
  access: roomAccessSchema.or(z.literal("")),
  // Optional to match the serializer (`RoomSerializer.beds` is `required=False`,
  // room.py:29): a room can be saved with just a name and filled in over time
  // (GAP-024). NOTE: `website_description`/`vc_notes` above stay `z.string()`
  // (not `.optional()`) — PATCH sends `""` to clear them; `.optional()` would
  // emit `undefined`, omit the field, and silently stop clearing.
  beds: roomBedsSchema.optional(),
  // Full-list sync: submitting the list replaces the room's amenity set;
  // ABSENT on PATCH leaves the links untouched (so absent ≠ clear — `[]`
  // clears, `undefined` skips).
  attribute_links: z
    .array(z.object({ attribute: z.number(), note: z.string().optional() }))
    .optional(),
});
export type PropertyRoomWriteInput = z.infer<typeof propertyRoomWriteInputSchema>;

export interface PropertyFilters {
  q?: string;
  country?: string;
  region?: string;
  collection?: string;
  min_bedrooms?: number;
  status?: string;
  ordering?: string;
  page?: number;
}

// Region/collection taxonomy now lives in lib/geo (GAP-072); re-exported here
// for intra-feature consumers that still import from properties/schemas.
export {
  regionSchema,
  regionsResponseSchema,
  collectionSchema,
  collectionsResponseSchema,
  type Region,
  type Collection,
} from "@/lib/geo/schemas";

// FK-picker rows for the create-property form (`GET /property-categories`).
// Only `id` + `name` are needed to pick; Zod strips the other serializer
// fields. Widen these when a consumer actually needs more.
export const propertyCategorySchema = z.object({
  id: z.number(),
  name: z.string(),
});
export type PropertyCategory = z.infer<typeof propertyCategorySchema>;

export const propertyCategoriesResponseSchema = paginated(propertyCategorySchema);

// Write shape for creating a property (GAP-049). Only the five fields the
// backend requires — `licence_number`/`channel`/`features`/`legacy_id` are
// optional or server-defaulted and are filled in later on the edit tabs
// (incremental-onboarding posture, GAP-024). FK fields default to the `0`
// sentinel so an unselected dropdown trips `.min(1)` with a required message.
export const propertyCreateInputSchema = z.object({
  name: z.string().trim().min(1, { message: "properties:create.errors.name_required" }).max(255),
  display_name: z
    .string()
    .trim()
    .min(1, { message: "properties:create.errors.display_name_required" })
    .max(255),
  slug: z
    .string()
    .trim()
    .min(1, { message: "properties:create.errors.slug_required" })
    .max(255)
    .regex(/^[a-z0-9-]+$/, { message: "properties:create.errors.slug_invalid" }),
  category: z.number().int().min(1, { message: "properties:create.errors.category_required" }),
  region: z.number().int().min(1, { message: "properties:create.errors.region_required" }),
});
export type PropertyCreateInput = z.infer<typeof propertyCreateInputSchema>;

export const rateBandSchema = z.object({
  id: z.number(),
  period: z.number(),
  min_party: z.number().nullable().optional(),
  max_party: z.number().nullable().optional(),
  nightly: z.string().nullable().optional(),
  weekly: z.string().nullable().optional(),
  is_poa: z.boolean().optional(),
  is_locked: z.boolean().optional(),
  is_approved: z.boolean().optional(),
  notes: z.string().nullable().optional(),
});
export type RateBand = z.infer<typeof rateBandSchema>;

export const ratePeriodSchema = z.object({
  id: z.number(),
  plan: z.number(),
  name: z.string().nullable().optional(),
  date_from: z.string(),
  date_to: z.string(),
  // Nullable per-period overrides of the villa default min/max-nights.
  min_nights: z.number().nullable().optional(),
  max_nights: z.number().nullable().optional(),
  is_active: z.boolean().optional(),
  bands: z.array(rateBandSchema).optional().default([]),
  // Read-only: uncovered `[low, high]` party sub-ranges of `1..max_occupancy`.
  coverage_gaps: z
    .array(z.tuple([z.number(), z.number()]))
    .optional()
    .default([]),
});
export type RatePeriod = z.infer<typeof ratePeriodSchema>;

export const ratePeriodWriteInputSchema = z
  .object({
    // GAP-056: the period owns the dates (inclusive) + nullable min/max-nights
    // overrides; its bands (RateBand) inherit its dates. GAP-059: the operator
    // label is compulsory.
    name: z
      .string()
      .trim()
      .min(1, { message: "properties:errors.rate_period_name_required" })
      .max(128),
    date_from: z.string().min(1, { message: "properties:errors.rate_period_date_from_required" }),
    date_to: z.string().min(1, { message: "properties:errors.rate_period_date_to_required" }),
    min_nights: z
      .number()
      .int()
      .min(1, { message: "properties:errors.rate_period_nights_min" })
      .nullable()
      .optional(),
    max_nights: z
      .number()
      .int()
      .min(1, { message: "properties:errors.rate_period_nights_min" })
      .nullable()
      .optional(),
    is_active: z.boolean().optional(),
  })
  // Dates are inclusive — a single-day period (date_from === date_to) is legal.
  .refine((v) => !v.date_from || !v.date_to || v.date_to >= v.date_from, {
    path: ["date_to"],
    message: "properties:errors.rate_period_date_to_before_from",
  })
  .refine((v) => v.max_nights == null || v.min_nights == null || v.max_nights >= v.min_nights, {
    path: ["max_nights"],
    message: "properties:errors.rate_period_max_nights_lt_min",
  });
export type RatePeriodWriteInput = z.infer<typeof ratePeriodWriteInputSchema>;

export const MONEY_PATTERN = /^\d{1,10}(\.\d{1,2})?$/;

export const rateBandWriteInputSchema = z
  .object({
    // GAP-056: a band is party x price only — its dates come from the period.
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
export type RateBandWriteInput = z.infer<typeof rateBandWriteInputSchema>;

/** Wire shape: empty/POA-masked money fields are sent as explicit nulls. */
export type RateBandWritePayload = Omit<RateBandWriteInput, "nightly" | "weekly"> & {
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
  prices_by_occupancy: z.boolean().optional(),
  effective_from: z.string().nullable().optional(),
  effective_to: z.string().nullable().optional(),
  is_active: z.boolean().optional(),
  notes: z.string().nullable().optional(),
});
export type RatePlan = z.infer<typeof ratePlanSchema>;

export const ratePlanDetailSchema = ratePlanSchema.extend({
  periods: z.array(ratePeriodSchema).optional().default([]),
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
  // An assignment points at exactly one of a Person (`contact`) or an
  // Organisation (`organisation`) — the `management_company` role uses the org
  // leg, so `contact` is null on those rows (GAP-048).
  contact: z.number().nullable(),
  organisation: z.number().nullable().optional(),
  organisation_detail: z.object({ id: z.number(), name: z.string() }).nullable().optional(),
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
  // Owning quotation of a quotation hold — read-only click-through, never an
  // edit affordance (that's what block_id signals).
  quotation_id: z.number().nullable().optional(),
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
  image_url: z.string().nullable().optional(),
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

export const propertyImageMetadataSchema = z.object({
  kind: z.enum(PROPERTY_IMAGE_KINDS),
  name: z.string().trim().max(255).optional(),
  description: z.string().trim().optional(),
  sort_order: z.number().int().min(0).optional(),
  is_active: z.boolean().optional(),
});
export type PropertyImageMetadataInput = z.infer<typeof propertyImageMetadataSchema>;

// Create = metadata + the file itself (multipart). Edit PATCHes metadata only.
export const propertyImageCreateInputSchema = propertyImageMetadataSchema.extend({
  image: z.instanceof(File, { message: "properties:errors.image_file_required" }),
});
export type PropertyImageCreateInput = z.infer<typeof propertyImageCreateInputSchema>;

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
    // Nullable so a cleared To can be sent as explicit `null` to CLEAR an
    // existing end date on PATCH (making the season open-ended). `.optional()`
    // alone would emit `undefined`, omit the field from the JSON body, and
    // silently keep the old end date — same trap as documented on
    // `propertyServiceWriteInputSchema` above.
    effective_to: z.string().nullable().optional(),
    is_active: z.boolean().optional(),
    prices_by_occupancy: z.boolean().optional(),
    notes: z.string().trim().optional(),
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
  // property has no location row yet.
  timezone: z.string().nullable().optional(),
  // Read-only effective currency as a string code (GAP-026): the currency
  // money inputs commit to. Null when the property sets no currency.
  currency_code: z.string().nullable().optional(),
  // GAP-034: the owner's online (non-iCal) calendar webpage; null when unset.
  calendar_url: z.string().nullable().optional(),
  // GAP-035 rate-entry derivation context (read-only). The effective default
  // basis pre-fills a new season's `price_basis`; the effective
  // commission + tax policy drive the rate-band form's net↔gross derivation.
  prices_entered_as_effective: z.string().nullable().optional(),
  commission: z
    .object({
      calculation_type: z.string().nullable().optional(),
      amount: z.string().nullable().optional(),
    })
    .nullable()
    .optional(),
  tax: z
    .object({
      percentage: z.string().nullable().optional(),
      is_exempt: z.boolean().nullable().optional(),
    })
    .nullable()
    .optional(),
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
  // GAP-034: the owner's online calendar webpage. The OperationalForm runs
  // `blankToNull` on submit, so a cleared input arrives as null. URL *format* is
  // validated server-side (Django `URLField`): the OperationalForm surfaces the
  // 400 through its `FormErrorAlert` (which renders messages verbatim, so a
  // client-side i18n-key zod message would leak as a raw key). Client-side we
  // only constrain the shape.
  calendar_url: z.string().nullable().optional(),
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
  // Nullable so an emptied tenure end can be sent as explicit `null` — DRF
  // rejects "" as an invalid date, and an omitted key would leave a
  // previously-set date uncleared on PATCH (see
  // `propertyServiceWriteInputSchema` above).
  start_date: z.string().nullable().optional(),
  end_date: z.string().nullable().optional(),
  is_primary: z.boolean().optional(),
});
export type PropertyContactAssignmentWriteInput = z.infer<
  typeof propertyContactAssignmentWriteInputSchema
>;
