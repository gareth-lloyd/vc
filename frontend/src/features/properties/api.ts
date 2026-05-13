import { apiGet } from "@/lib/api/client";
import type { QueryParams } from "@/lib/api/url";
import {
  propertyDescriptionsResponseSchema,
  propertyDetailSchema,
  propertyFeaturesResponseSchema,
  propertyListResponseSchema,
  propertyRoomsResponseSchema,
  type PropertyDescription,
  type PropertyDetail,
  type PropertyFeature,
  type PropertyFilters,
  type PropertyListItem,
  type PropertyRoom,
} from "./schemas";
import type { Paginated } from "@/types/api";
import type { PropertyId } from "@/lib/query/keys";

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
