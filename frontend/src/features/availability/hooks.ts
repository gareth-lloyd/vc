import { useQuery } from "@tanstack/react-query";
import { queryKeys } from "@/lib/query/keys";
import { fetchProperties } from "@/features/properties/api";
import type { PropertyFilters } from "@/features/properties/schemas";
import { fetchMultiAvailability, fetchWeeklyPrices } from "./api";
import { hasAnyFilter, type TimelineFilters } from "./schemas";

/**
 * The timeline's villa rows — one page of `GET /properties`, sharing the
 * list page's cache. Two pinned behaviours (see the page tests):
 *
 * - Disabled until at least one filter is set (the force-filter gate; the
 *   prompt-first UX is a client choice, the API stays open).
 * - NEVER carries `date_from`/`date_to`: `PropertyFilter` treats a date
 *   window as an availability *exclusion*, which would hide exactly the
 *   booked villas the timeline exists to show.
 */
export function useTimelineProperties(filters: TimelineFilters) {
  const propertyFilters: PropertyFilters = {
    q: filters.q,
    country: filters.country,
    region: filters.region,
    collection: filters.collection,
    min_bedrooms: filters.min_bedrooms,
    status: filters.status,
    page: filters.page,
    // No `ordering` param: the model's Meta ordering is already the total
    // order ["name", "id"]. An explicit `ordering=name` would *replace* it
    // wholesale and lose the id tiebreaker — duplicate names would then
    // paginate non-deterministically across pages.
  };
  return useQuery({
    queryKey: queryKeys.properties.list(propertyFilters),
    queryFn: () => fetchProperties(propertyFilters),
    enabled: hasAnyFilter(filters),
  });
}

export function useMultiAvailability(propertyIds: number[], from: string, to: string) {
  return useQuery({
    queryKey: queryKeys.availability.timeline(propertyIds, from, to),
    queryFn: () => fetchMultiAvailability(propertyIds, from, to),
    enabled: propertyIds.length > 0,
  });
}

/**
 * Per-week guide prices for the timeline (GAP-030) — a SEPARATE query from the
 * bands so the price strip fills in after the (faster) availability bands,
 * never blocking them. Same id/window gate as `useMultiAvailability`.
 */
export function useWeeklyPrices(propertyIds: number[], from: string, to: string) {
  return useQuery({
    queryKey: queryKeys.availability.weeklyPrices(propertyIds, from, to),
    queryFn: () => fetchWeeklyPrices(propertyIds, from, to),
    enabled: propertyIds.length > 0,
  });
}
