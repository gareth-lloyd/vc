import { apiGet, apiSend } from "@/lib/api/client";
import type { QueryParams } from "@/lib/api/url";
import {
  availabilityCalendarResponseSchema,
  availabilityHoldsResponseSchema,
  availabilityHoldSchema,
  changeOverRuleSchema,
  changeOverRulesResponseSchema,
  collectionsResponseSchema,
  propertyCategoriesResponseSchema,
  propertyGroupsResponseSchema,
  regionsResponseSchema,
  discountsResponseSchema,
  extrasResponseSchema,
  propertyBookingsResponseSchema,
  propertyCapacitySchema,
  propertyContactsResponseSchema,
  propertyDescriptionSchema,
  propertyDescriptionsResponseSchema,
  propertyDetailSchema,
  propertyFinanceSchema,
  nearbyPlaceTypesResponseSchema,
  propertyImageSchema,
  propertyImagesResponseSchema,
  propertyListResponseSchema,
  propertyLocationSchema,
  propertyNearbyPlaceSchema,
  propertyNearbyPlacesResponseSchema,
  propertyServiceSchema,
  propertyServicesResponseSchema,
  propertyRoomSchema,
  propertyRoomsResponseSchema,
  propertySettingsSchema,
  ratePeriodSchema,
  ratePlanDetailSchema,
  ratePlanSchema,
  ratePlansResponseSchema,
  rateBandSchema,
  sectionToSlug,
  type AvailabilityBlockWriteInput,
  type AvailabilityCalendarResponse,
  type AvailabilityHold,
  type ChangeOverRule,
  type ChangeOverRuleWriteInput,
  type Collection,
  type DescriptionSection,
  type Discount,
  type Extra,
  type NearbyPlaceType,
  type PropertyBookingItem,
  type PropertyCapacity,
  type PropertyCapacityWriteInput,
  type PropertyContactAssignment,
  propertyContactAssignmentSchema,
  type PropertyContactAssignmentWriteInput,
  type PropertyCategory,
  type PropertyCreateInput,
  type PropertyDescription,
  type PropertyDetail,
  type PropertyGroup,
  type PropertyFilters,
  type PropertyFinance,
  type PropertyFinanceWriteInput,
  type PropertyImage,
  type PropertyImageCreateInput,
  type PropertyListItem,
  type PropertyLocation,
  type PropertyLocationWriteInput,
  type Region,
  type PropertyNearbyPlace,
  type PropertyNearbyPlaceWriteInput,
  type PropertyService,
  type PropertyServiceWriteInput,
  type PropertyRoom,
  type PropertyRoomWriteInput,
  type PropertySettings,
  type PropertySettingsWriteInput,
  type RatePeriod,
  type RatePeriodWriteInput,
  type RatePlan,
  type RatePlanDetail,
  type RatePlanWriteInput,
  type RateBand,
  type RateBandWritePayload,
} from "./schemas";
import type { Paginated } from "@/types/api";
import type { PropertyId, RatePlanId } from "@/lib/query/keys";

function toQuery(filters: PropertyFilters): QueryParams {
  return {
    q: filters.q || undefined,
    country: filters.country || undefined,
    region: filters.region || undefined,
    collection: filters.collection || undefined,
    min_bedrooms: filters.min_bedrooms || undefined,
    status: filters.status || undefined,
    ordering: filters.ordering || undefined,
    page: filters.page && filters.page > 1 ? filters.page : undefined,
  };
}

export async function fetchProperties(
  filters: PropertyFilters,
): Promise<Paginated<PropertyListItem>> {
  const data = await apiGet<unknown>("/properties", { query: toQuery(filters) });
  return propertyListResponseSchema.parse(data);
}

export async function fetchProperty(idOrSlug: PropertyId): Promise<PropertyDetail> {
  const data = await apiGet<unknown>(`/properties/${idOrSlug}`);
  return propertyDetailSchema.parse(data);
}

export async function createProperty(body: PropertyCreateInput): Promise<PropertyDetail> {
  // The viewset re-serialises the created row with the detail serializer and
  // returns 201, so the response parses with `propertyDetailSchema`.
  const data = await apiSend<unknown>("POST", "/properties", body);
  return propertyDetailSchema.parse(data);
}

export async function fetchPropertyDescriptions(
  idOrSlug: PropertyId,
): Promise<Paginated<PropertyDescription>> {
  const data = await apiGet<unknown>(`/properties/${idOrSlug}/descriptions`);
  return propertyDescriptionsResponseSchema.parse(data);
}

export async function upsertPropertyDescription(
  propertyId: PropertyId,
  section: DescriptionSection,
  body: string,
): Promise<PropertyDescription> {
  const data = await apiSend<unknown>(
    "PUT",
    `/properties/${propertyId}/descriptions/${sectionToSlug(section)}`,
    { body },
  );
  return propertyDescriptionSchema.parse(data);
}

export async function deletePropertyDescription(
  propertyId: PropertyId,
  section: DescriptionSection,
): Promise<void> {
  await apiSend<void>("DELETE", `/properties/${propertyId}/descriptions/${sectionToSlug(section)}`);
}

export async function fetchChangeOverRules(
  propertyId: PropertyId,
  effectiveOn?: string,
): Promise<Paginated<ChangeOverRule>> {
  const query = effectiveOn ? { effective_on: effectiveOn } : undefined;
  const data = await apiGet<unknown>(`/properties/${propertyId}/change-over-rules`, { query });
  return changeOverRulesResponseSchema.parse(data);
}

export async function createChangeOverRule(
  propertyId: PropertyId,
  body: ChangeOverRuleWriteInput,
): Promise<ChangeOverRule> {
  const data = await apiSend<unknown>("POST", `/properties/${propertyId}/change-over-rules`, body);
  return changeOverRuleSchema.parse(data);
}

export async function updateChangeOverRule(
  ruleId: number,
  body: Partial<ChangeOverRuleWriteInput>,
): Promise<ChangeOverRule> {
  const data = await apiSend<unknown>("PATCH", `/change-over-rules/${ruleId}`, body);
  return changeOverRuleSchema.parse(data);
}

export async function deleteChangeOverRule(ruleId: number): Promise<void> {
  await apiSend<void>("DELETE", `/change-over-rules/${ruleId}`);
}

export async function fetchPropertyRooms(idOrSlug: PropertyId): Promise<Paginated<PropertyRoom>> {
  const data = await apiGet<unknown>(`/properties/${idOrSlug}/rooms`);
  return propertyRoomsResponseSchema.parse(data);
}

export async function createPropertyRoom(
  propertyId: PropertyId,
  body: PropertyRoomWriteInput,
): Promise<PropertyRoom> {
  const data = await apiSend<unknown>("POST", `/properties/${propertyId}/rooms`, body);
  return propertyRoomSchema.parse(data);
}

export async function updatePropertyRoom(
  propertyId: PropertyId,
  roomId: number,
  body: Partial<PropertyRoomWriteInput>,
): Promise<PropertyRoom> {
  const data = await apiSend<unknown>("PATCH", `/properties/${propertyId}/rooms/${roomId}`, body);
  return propertyRoomSchema.parse(data);
}

export async function deletePropertyRoom(propertyId: PropertyId, roomId: number): Promise<void> {
  await apiSend<void>("DELETE", `/properties/${propertyId}/rooms/${roomId}`);
}

export async function reorderPropertyRooms(
  propertyId: PropertyId,
  roomIds: number[],
): Promise<void> {
  await apiSend<unknown>("POST", `/properties/${propertyId}/rooms:reorder`, {
    room_ids: roomIds,
  });
}

export async function fetchNearbyPlaceTypes(): Promise<Paginated<NearbyPlaceType>> {
  const data = await apiGet<unknown>("/nearby-place-types");
  return nearbyPlaceTypesResponseSchema.parse(data);
}

export async function fetchPropertyNearbyPlaces(
  propertyId: PropertyId,
): Promise<Paginated<PropertyNearbyPlace>> {
  const data = await apiGet<unknown>(`/properties/${propertyId}/nearby`);
  return propertyNearbyPlacesResponseSchema.parse(data);
}

export async function createPropertyNearbyPlace(
  propertyId: PropertyId,
  body: PropertyNearbyPlaceWriteInput,
): Promise<PropertyNearbyPlace> {
  const data = await apiSend<unknown>("POST", `/properties/${propertyId}/nearby`, body);
  return propertyNearbyPlaceSchema.parse(data);
}

export async function updatePropertyNearbyPlace(
  propertyId: PropertyId,
  poiId: number,
  body: Partial<PropertyNearbyPlaceWriteInput> & { sort_order?: number },
): Promise<PropertyNearbyPlace> {
  const data = await apiSend<unknown>("PATCH", `/properties/${propertyId}/nearby/${poiId}`, body);
  return propertyNearbyPlaceSchema.parse(data);
}

export async function deletePropertyNearbyPlace(
  propertyId: PropertyId,
  poiId: number,
): Promise<void> {
  await apiSend<void>("DELETE", `/properties/${propertyId}/nearby/${poiId}`);
}

export async function fetchPropertyServices(
  propertyId: PropertyId,
): Promise<Paginated<PropertyService>> {
  const data = await apiGet<unknown>(`/properties/${propertyId}/services`);
  return propertyServicesResponseSchema.parse(data);
}

export async function createPropertyService(
  propertyId: PropertyId,
  body: PropertyServiceWriteInput,
): Promise<PropertyService> {
  const data = await apiSend<unknown>("POST", `/properties/${propertyId}/services`, body);
  return propertyServiceSchema.parse(data);
}

// The detail endpoint is flat (`/services/{id}`), not nested under the property
// — see properties/urls.py. Only the create/list routes are property-scoped.
export async function updatePropertyService(
  serviceId: number,
  body: Partial<PropertyServiceWriteInput> & { sort_order?: number },
): Promise<PropertyService> {
  const data = await apiSend<unknown>("PATCH", `/services/${serviceId}`, body);
  return propertyServiceSchema.parse(data);
}

export async function deletePropertyService(serviceId: number): Promise<void> {
  await apiSend<void>("DELETE", `/services/${serviceId}`);
}

export async function fetchPropertyRatePlans(idOrSlug: PropertyId): Promise<Paginated<RatePlan>> {
  const data = await apiGet<unknown>(`/properties/${idOrSlug}/rate-plans`);
  return ratePlansResponseSchema.parse(data);
}

export async function fetchRatePlanDetail(ratePlanId: RatePlanId): Promise<RatePlanDetail> {
  const data = await apiGet<unknown>(`/rate-plans/${ratePlanId}`);
  return ratePlanDetailSchema.parse(data);
}

export async function createRatePlan(
  propertyId: PropertyId,
  body: RatePlanWriteInput,
): Promise<RatePlan> {
  const data = await apiSend<unknown>("POST", `/properties/${propertyId}/rate-plans`, body);
  return ratePlanSchema.parse(data);
}

export async function updateRatePlan(
  ratePlanId: RatePlanId,
  body: Partial<RatePlanWriteInput>,
): Promise<RatePlan> {
  const data = await apiSend<unknown>("PATCH", `/rate-plans/${ratePlanId}`, body);
  return ratePlanSchema.parse(data);
}

export async function deleteRatePlan(ratePlanId: RatePlanId): Promise<void> {
  await apiSend<void>("DELETE", `/rate-plans/${ratePlanId}`);
}

export async function duplicateRatePlan(ratePlanId: RatePlanId): Promise<RatePlan> {
  const data = await apiSend<unknown>("POST", `/rate-plans/${ratePlanId}:duplicate`);
  return ratePlanSchema.parse(data);
}

export async function createRatePeriod(
  ratePlanId: RatePlanId,
  body: RatePeriodWriteInput,
): Promise<RatePeriod> {
  const data = await apiSend<unknown>("POST", `/rate-plans/${ratePlanId}/rate-periods`, body);
  return ratePeriodSchema.parse(data);
}

export async function updateRatePeriod(
  periodId: number,
  body: Partial<RatePeriodWriteInput>,
): Promise<RatePeriod> {
  const data = await apiSend<unknown>("PATCH", `/periods/${periodId}`, body);
  return ratePeriodSchema.parse(data);
}

export async function deleteRatePeriod(periodId: number): Promise<void> {
  await apiSend<void>("DELETE", `/periods/${periodId}`);
}

export async function createRateBand(
  periodId: number,
  body: RateBandWritePayload,
): Promise<RateBand> {
  const data = await apiSend<unknown>("POST", `/periods/${periodId}/bands`, body);
  return rateBandSchema.parse(data);
}

export async function updateRateBand(
  bandId: number,
  body: Partial<RateBandWritePayload>,
): Promise<RateBand> {
  const data = await apiSend<unknown>("PATCH", `/bands/${bandId}`, body);
  return rateBandSchema.parse(data);
}

export async function deleteRateBand(bandId: number): Promise<void> {
  await apiSend<void>("DELETE", `/bands/${bandId}`);
}

export async function fetchPropertyExtras(idOrSlug: PropertyId): Promise<Paginated<Extra>> {
  const data = await apiGet<unknown>(`/properties/${idOrSlug}/extras`);
  return extrasResponseSchema.parse(data);
}

export async function fetchPropertyDiscounts(idOrSlug: PropertyId): Promise<Paginated<Discount>> {
  const data = await apiGet<unknown>(`/properties/${idOrSlug}/discounts`);
  return discountsResponseSchema.parse(data);
}

export async function fetchPropertyContacts(
  idOrSlug: PropertyId,
): Promise<Paginated<PropertyContactAssignment>> {
  const data = await apiGet<unknown>(`/properties/${idOrSlug}/contacts`);
  return propertyContactsResponseSchema.parse(data);
}

// Filter dropdowns need every row in one request — the default page size of
// 50 would silently truncate the lists as the portfolio grows. Exported for
// callers whose fetch layer doesn't bake it in (e.g. the countries lookup).
export const TAXONOMY_PAGE_SIZE = 500;

export interface RegionListFilters {
  // Only regions that actually hold properties (quote-builder criteria
  // dropdown); server-side opt-in narrowing, false behaves like absent.
  hasProperties?: boolean;
  // Scope to one country: `country` is the FK id, `countryIso2` the
  // case-insensitive ISO code — pass whichever the caller holds.
  country?: number;
  countryIso2?: string;
}

export async function fetchRegions(filters: RegionListFilters = {}): Promise<Paginated<Region>> {
  const data = await apiGet<unknown>("/regions", {
    query: {
      ordering: "name",
      page_size: TAXONOMY_PAGE_SIZE,
      has_properties: filters.hasProperties || undefined,
      country: filters.country,
      country_iso2: filters.countryIso2,
    },
  });
  return regionsResponseSchema.parse(data);
}

export async function fetchCollections(): Promise<Paginated<Collection>> {
  const data = await apiGet<unknown>("/collections", {
    query: { ordering: "name", page_size: TAXONOMY_PAGE_SIZE },
  });
  return collectionsResponseSchema.parse(data);
}

export async function fetchPropertyCategories(): Promise<Paginated<PropertyCategory>> {
  // Model `Meta.ordering` already sorts by (sort_order, name); fetch the whole
  // catalogue for the create-form picker (`page_size` guards against growth).
  const data = await apiGet<unknown>("/property-categories", {
    query: { page_size: TAXONOMY_PAGE_SIZE },
  });
  return propertyCategoriesResponseSchema.parse(data);
}

export async function fetchPropertyGroups(): Promise<Paginated<PropertyGroup>> {
  const data = await apiGet<unknown>("/property-groups", {
    query: { page_size: TAXONOMY_PAGE_SIZE },
  });
  return propertyGroupsResponseSchema.parse(data);
}

export async function fetchPropertyHolds(
  propertyId: number,
  from: string,
  to: string,
): Promise<AvailabilityHold[]> {
  const data = await apiGet<unknown>("/availability", {
    query: { property_ids: propertyId, from, to },
  });
  return availabilityHoldsResponseSchema.parse(data).records;
}

export async function fetchPropertyBookingsForRange(
  propertyId: number,
  from: string,
  to: string,
): Promise<Paginated<PropertyBookingItem>> {
  const data = await apiGet<unknown>("/bookings", {
    query: { property: propertyId, check_in_before: to, check_out_after: from },
  });
  return propertyBookingsResponseSchema.parse(data);
}

export async function fetchPropertyAvailabilityCells(
  propertyId: number,
  from: string,
  to: string,
): Promise<AvailabilityCalendarResponse> {
  const data = await apiGet<unknown>(`/properties/${propertyId}/availability`, {
    query: { from, to },
  });
  return availabilityCalendarResponseSchema.parse(data);
}

export async function createPropertyBlock(
  propertyId: number,
  body: AvailabilityBlockWriteInput,
): Promise<AvailabilityHold> {
  const data = await apiSend<unknown>("POST", `/properties/${propertyId}/availability`, body);
  return availabilityHoldSchema.parse(data);
}

export async function updatePropertyBlock(
  blockId: number,
  body: Partial<AvailabilityBlockWriteInput>,
): Promise<AvailabilityHold> {
  const data = await apiSend<unknown>("PATCH", `/availability/${blockId}`, body);
  return availabilityHoldSchema.parse(data);
}

export async function deletePropertyBlock(blockId: number): Promise<void> {
  await apiSend<void>("DELETE", `/availability/${blockId}`);
}

export async function createPropertyContact(
  propertyId: PropertyId,
  body: PropertyContactAssignmentWriteInput,
): Promise<PropertyContactAssignment> {
  const data = await apiSend<unknown>("POST", `/properties/${propertyId}/contacts`, body);
  return propertyContactAssignmentSchema.parse(data);
}

export async function updatePropertyContact(
  propertyId: PropertyId,
  mappingId: number,
  body: Partial<PropertyContactAssignmentWriteInput>,
): Promise<PropertyContactAssignment> {
  const data = await apiSend<unknown>(
    "PATCH",
    `/properties/${propertyId}/contacts/${mappingId}`,
    body,
  );
  return propertyContactAssignmentSchema.parse(data);
}

export async function deletePropertyContact(
  propertyId: PropertyId,
  mappingId: number,
): Promise<void> {
  await apiSend<void>("DELETE", `/properties/${propertyId}/contacts/${mappingId}`);
}

export async function fetchPropertyImages(propertyId: number): Promise<Paginated<PropertyImage>> {
  const data = await apiGet<unknown>(`/properties/${propertyId}/images`);
  return propertyImagesResponseSchema.parse(data);
}

export async function createPropertyImage(
  propertyId: number,
  input: PropertyImageCreateInput,
): Promise<PropertyImage> {
  const form = new FormData();
  form.append("image", input.image);
  form.append("kind", input.kind);
  if (input.name !== undefined) form.append("name", input.name);
  if (input.description !== undefined) form.append("description", input.description);
  if (input.sort_order !== undefined) form.append("sort_order", String(input.sort_order));
  if (input.is_active !== undefined) form.append("is_active", String(input.is_active));
  const data = await apiSend<unknown>("POST", `/properties/${propertyId}/images`, form);
  return propertyImageSchema.parse(data);
}

export async function updatePropertyImage(
  propertyId: number,
  imageId: number,
  body: Partial<{
    kind: string;
    name: string;
    description: string;
    sort_order: number;
    is_active: boolean;
  }>,
): Promise<PropertyImage> {
  const data = await apiSend<unknown>("PATCH", `/properties/${propertyId}/images/${imageId}`, body);
  return propertyImageSchema.parse(data);
}

export async function deletePropertyImage(propertyId: number, imageId: number): Promise<void> {
  await apiSend<void>("DELETE", `/properties/${propertyId}/images/${imageId}`);
}

export async function reorderPropertyImages(propertyId: number, imageIds: number[]): Promise<void> {
  await apiSend<unknown>("POST", `/properties/${propertyId}/images:reorder`, {
    image_ids: imageIds,
  });
}

export async function setPropertyImageHero(propertyId: number, imageId: number): Promise<void> {
  await apiSend<unknown>("POST", `/properties/${propertyId}/images:set-hero`, {
    image_id: imageId,
  });
}

export async function fetchPropertySettings(propertyId: number): Promise<PropertySettings> {
  const data = await apiGet<unknown>(`/properties/${propertyId}/settings`);
  return propertySettingsSchema.parse(data);
}

export async function updatePropertySettings(
  propertyId: number,
  body: PropertySettingsWriteInput,
): Promise<PropertySettings> {
  const data = await apiSend<unknown>("PATCH", `/properties/${propertyId}/settings`, body);
  return propertySettingsSchema.parse(data);
}

export async function fetchPropertyCapacity(propertyId: number): Promise<PropertyCapacity> {
  const data = await apiGet<unknown>(`/properties/${propertyId}/capacity`);
  return propertyCapacitySchema.parse(data);
}

export async function updatePropertyCapacity(
  propertyId: number,
  body: PropertyCapacityWriteInput,
): Promise<PropertyCapacity> {
  const data = await apiSend<unknown>("PATCH", `/properties/${propertyId}/capacity`, body);
  return propertyCapacitySchema.parse(data);
}

export async function fetchPropertyFinance(propertyId: number): Promise<PropertyFinance> {
  const data = await apiGet<unknown>(`/properties/${propertyId}/finance`);
  return propertyFinanceSchema.parse(data);
}

export async function updatePropertyFinance(
  propertyId: number,
  body: PropertyFinanceWriteInput,
): Promise<PropertyFinance> {
  const data = await apiSend<unknown>("PATCH", `/properties/${propertyId}/finance`, body);
  return propertyFinanceSchema.parse(data);
}

export async function fetchPropertyLocation(propertyId: number): Promise<PropertyLocation> {
  const data = await apiGet<unknown>(`/properties/${propertyId}/location`);
  return propertyLocationSchema.parse(data);
}

export async function updatePropertyLocation(
  propertyId: number,
  body: PropertyLocationWriteInput,
): Promise<PropertyLocation> {
  const data = await apiSend<unknown>("PATCH", `/properties/${propertyId}/location`, body);
  return propertyLocationSchema.parse(data);
}

export async function updatePropertyFeatures(
  propertyId: PropertyId,
  featureIds: number[],
): Promise<PropertyDetail> {
  const data = await apiSend<unknown>("PATCH", `/properties/${propertyId}`, {
    features: featureIds,
  });
  return propertyDetailSchema.parse(data);
}

export async function activateProperty(idOrSlug: PropertyId): Promise<PropertyDetail> {
  const data = await apiSend<unknown>("POST", `/properties/${idOrSlug}:activate`);
  return propertyDetailSchema.parse(data);
}

export async function archiveProperty(idOrSlug: PropertyId): Promise<PropertyDetail> {
  const data = await apiSend<unknown>("POST", `/properties/${idOrSlug}:archive`);
  return propertyDetailSchema.parse(data);
}

export async function restoreProperty(idOrSlug: PropertyId): Promise<PropertyDetail> {
  const data = await apiSend<unknown>("POST", `/properties/${idOrSlug}:restore`);
  return propertyDetailSchema.parse(data);
}

// GAP-033: staff "Mark as up-to-date" — stamps the confirmed-by-VC-staff signal
// (Signal 3) without adding any dates. Returns the updated detail payload.
export async function confirmPropertyAvailability(idOrSlug: PropertyId): Promise<PropertyDetail> {
  const data = await apiSend<unknown>("POST", `/properties/${idOrSlug}:confirm-availability`);
  return propertyDetailSchema.parse(data);
}
