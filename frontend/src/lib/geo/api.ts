// Read-side fetchers for shared geo/taxonomy data (GAP-072). The country WRITE
// path (create/update/delete + the detail fetch) stays in admin/countries —
// only the list reads that feed cross-feature dropdowns live here.
import { apiGet } from "@/lib/api/client";
import type { QueryParams } from "@/lib/api/url";
import type { Paginated } from "@/types/api";
import {
  collectionsResponseSchema,
  countriesListResponseSchema,
  regionsResponseSchema,
  type Collection,
  type Country,
  type CountryFilters,
  type Region,
  type RegionListFilters,
} from "./schemas";

// Filter dropdowns need every row in one request — the default page size of
// 50 would silently truncate the lists as the portfolio grows. Exported for
// callers whose fetch layer doesn't bake it in (e.g. the countries lookup).
export const TAXONOMY_PAGE_SIZE = 500;

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

function countryToQuery(filters: CountryFilters): QueryParams {
  return {
    search: filters.search || undefined,
    ordering: filters.ordering || undefined,
    page: filters.page && filters.page > 1 ? filters.page : undefined,
    page_size: filters.pageSize || undefined,
    has_properties: filters.hasProperties || undefined,
  };
}

export async function fetchCountries(filters: CountryFilters): Promise<Paginated<Country>> {
  const data = await apiGet<unknown>("/countries", { query: countryToQuery(filters) });
  return countriesListResponseSchema.parse(data);
}
