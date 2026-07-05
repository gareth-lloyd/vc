// React Query hooks for shared geo/taxonomy reads (GAP-072). Query keys stay
// central in lib/query/keys. The country DETAIL hook and the CRUD mutations
// live in admin/countries — only the list reads shared across features are here.
import { useQuery } from "@tanstack/react-query";
import { queryKeys } from "@/lib/query/keys";
import { fetchCollections, fetchCountries, fetchRegions } from "./api";
import type { CountryFilters, RegionListFilters } from "./schemas";

export function useRegions(filters?: RegionListFilters) {
  return useQuery({
    queryKey: queryKeys.regions.list(filters),
    queryFn: () => fetchRegions(filters),
  });
}

export function useCollections() {
  return useQuery({ queryKey: queryKeys.collections.list(), queryFn: fetchCollections });
}

export function useCountries(filters: CountryFilters) {
  return useQuery({
    queryKey: queryKeys.countries.list(filters),
    queryFn: () => fetchCountries(filters),
  });
}
