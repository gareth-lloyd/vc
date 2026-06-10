import { apiGet, apiSend } from "@/lib/api/client";
import type { QueryParams } from "@/lib/api/url";
import {
  availabilityCalendarResponseSchema,
  availabilityHoldsResponseSchema,
  availabilityHoldSchema,
  changeOverRuleSchema,
  changeOverRulesResponseSchema,
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
  propertyRoomSchema,
  propertyRoomsResponseSchema,
  propertySettingsSchema,
  rateCardSchema,
  ratePlanDetailSchema,
  ratePlanSchema,
  ratePlansResponseSchema,
  rateRuleSchema,
  sectionToSlug,
  type AvailabilityBlockWriteInput,
  type AvailabilityCalendarResponse,
  type AvailabilityHold,
  type ChangeOverRule,
  type ChangeOverRuleWriteInput,
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
  type PropertyDescription,
  type PropertyDetail,
  type PropertyFilters,
  type PropertyFinance,
  type PropertyFinanceWriteInput,
  type PropertyImage,
  type PropertyImageCreateInput,
  type PropertyListItem,
  type PropertyLocation,
  type PropertyLocationWriteInput,
  type PropertyNearbyPlace,
  type PropertyNearbyPlaceWriteInput,
  type PropertyRoom,
  type PropertyRoomWriteInput,
  type PropertySettings,
  type PropertySettingsWriteInput,
  type RateCard,
  type RateCardWriteInput,
  type RatePlan,
  type RatePlanDetail,
  type RatePlanWriteInput,
  type RateRule,
  type RateRuleWritePayload,
} from "./schemas";
import type { Paginated } from "@/types/api";
import type { PropertyId, SeasonId } from "@/lib/query/keys";

function toQuery(filters: PropertyFilters): QueryParams {
  return {
    q: filters.q || undefined,
    country: filters.country || undefined,
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

export async function fetchPropertySeasons(idOrSlug: PropertyId): Promise<Paginated<RatePlan>> {
  const data = await apiGet<unknown>(`/properties/${idOrSlug}/seasons`);
  return ratePlansResponseSchema.parse(data);
}

export async function fetchSeasonDetail(seasonId: SeasonId): Promise<RatePlanDetail> {
  const data = await apiGet<unknown>(`/seasons/${seasonId}`);
  return ratePlanDetailSchema.parse(data);
}

export async function createSeason(
  propertyId: PropertyId,
  body: RatePlanWriteInput,
): Promise<RatePlan> {
  const data = await apiSend<unknown>("POST", `/properties/${propertyId}/seasons`, body);
  return ratePlanSchema.parse(data);
}

export async function updateSeason(
  seasonId: SeasonId,
  body: Partial<RatePlanWriteInput>,
): Promise<RatePlan> {
  const data = await apiSend<unknown>("PATCH", `/seasons/${seasonId}`, body);
  return ratePlanSchema.parse(data);
}

export async function deleteSeason(seasonId: SeasonId): Promise<void> {
  await apiSend<void>("DELETE", `/seasons/${seasonId}`);
}

export async function duplicateSeason(seasonId: SeasonId): Promise<RatePlan> {
  const data = await apiSend<unknown>("POST", `/seasons/${seasonId}:duplicate`);
  return ratePlanSchema.parse(data);
}

export async function createRateCard(
  seasonId: SeasonId,
  body: RateCardWriteInput,
): Promise<RateCard> {
  const data = await apiSend<unknown>("POST", `/seasons/${seasonId}/rate-cards`, body);
  return rateCardSchema.parse(data);
}

export async function updateRateCard(
  cardId: number,
  body: Partial<RateCardWriteInput>,
): Promise<RateCard> {
  const data = await apiSend<unknown>("PATCH", `/rate-cards/${cardId}`, body);
  return rateCardSchema.parse(data);
}

export async function deleteRateCard(cardId: number): Promise<void> {
  await apiSend<void>("DELETE", `/rate-cards/${cardId}`);
}

export async function duplicateRateCard(cardId: number): Promise<RateCard> {
  const data = await apiSend<unknown>("POST", `/rate-cards/${cardId}:duplicate`);
  return rateCardSchema.parse(data);
}

export async function createRateRule(
  cardId: number,
  body: RateRuleWritePayload,
): Promise<RateRule> {
  const data = await apiSend<unknown>("POST", `/rate-cards/${cardId}/rules`, body);
  return rateRuleSchema.parse(data);
}

export async function updateRateRule(
  ruleId: number,
  body: Partial<RateRuleWritePayload>,
): Promise<RateRule> {
  const data = await apiSend<unknown>("PATCH", `/rules/${ruleId}`, body);
  return rateRuleSchema.parse(data);
}

export async function deleteRateRule(ruleId: number): Promise<void> {
  await apiSend<void>("DELETE", `/rules/${ruleId}`);
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
