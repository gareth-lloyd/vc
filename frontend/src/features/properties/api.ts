import { apiGet, apiSend } from "@/lib/api/client";
import type { QueryParams } from "@/lib/api/url";
import {
  availabilityHoldsResponseSchema,
  discountsResponseSchema,
  extrasResponseSchema,
  propertyBookingsResponseSchema,
  propertyContactsResponseSchema,
  propertyDescriptionsResponseSchema,
  propertyDetailSchema,
  propertyFeaturesResponseSchema,
  propertyFinanceSchema,
  propertyImageSchema,
  propertyImagesResponseSchema,
  propertyListResponseSchema,
  propertyRoomsResponseSchema,
  propertySettingsSchema,
  ratePlanDetailSchema,
  ratePlansResponseSchema,
  type AvailabilityHold,
  type Discount,
  type Extra,
  type PropertyBookingItem,
  type PropertyContactAssignment,
  propertyContactAssignmentSchema,
  type PropertyContactAssignmentWriteInput,
  type PropertyDescription,
  type PropertyDetail,
  type PropertyFeature,
  type PropertyFilters,
  type PropertyFinance,
  type PropertyFinanceWriteInput,
  type PropertyImage,
  type PropertyImageWriteInput,
  type PropertyListItem,
  type PropertyRoom,
  type PropertySettings,
  type PropertySettingsWriteInput,
  type RatePlan,
  type RatePlanDetail,
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

export async function fetchPropertyFeatures(
  idOrSlug: PropertyId,
): Promise<Paginated<PropertyFeature>> {
  const data = await apiGet<unknown>(`/properties/${idOrSlug}/features`);
  return propertyFeaturesResponseSchema.parse(data);
}

export async function fetchPropertyRooms(idOrSlug: PropertyId): Promise<Paginated<PropertyRoom>> {
  const data = await apiGet<unknown>(`/properties/${idOrSlug}/rooms`);
  return propertyRoomsResponseSchema.parse(data);
}

export async function fetchPropertySeasons(idOrSlug: PropertyId): Promise<Paginated<RatePlan>> {
  const data = await apiGet<unknown>(`/properties/${idOrSlug}/seasons`);
  return ratePlansResponseSchema.parse(data);
}

export async function fetchSeasonDetail(seasonId: SeasonId): Promise<RatePlanDetail> {
  const data = await apiGet<unknown>(`/seasons/${seasonId}`);
  return ratePlanDetailSchema.parse(data);
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
  body: PropertyImageWriteInput,
): Promise<PropertyImage> {
  const data = await apiSend<unknown>("POST", `/properties/${propertyId}/images`, body);
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
