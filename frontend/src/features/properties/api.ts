import { apiGet } from "@/lib/api/client";
import type { QueryParams } from "@/lib/api/url";
import {
  contactSchema,
  discountsResponseSchema,
  extrasResponseSchema,
  propertyContactsResponseSchema,
  propertyDescriptionsResponseSchema,
  propertyDetailSchema,
  propertyFeaturesResponseSchema,
  propertyListResponseSchema,
  propertyRoomsResponseSchema,
  ratePlanDetailSchema,
  ratePlansResponseSchema,
  type Contact,
  type Discount,
  type Extra,
  type PropertyContactAssignment,
  type PropertyDescription,
  type PropertyDetail,
  type PropertyFeature,
  type PropertyFilters,
  type PropertyListItem,
  type PropertyRoom,
  type RatePlan,
  type RatePlanDetail,
} from "./schemas";
import type { Paginated } from "@/types/api";
import type { ContactId, PropertyId, SeasonId } from "@/lib/query/keys";

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

export async function fetchContact(id: ContactId): Promise<Contact> {
  const data = await apiGet<unknown>(`/contacts/${id}`);
  return contactSchema.parse(data);
}
