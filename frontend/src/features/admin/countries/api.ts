import { apiGet, apiSend } from "@/lib/api/client";
import type { QueryParams } from "@/lib/api/url";
import type { Paginated } from "@/types/api";
import {
  countriesListResponseSchema,
  countrySchema,
  type Country,
  type CountryFilters,
  type CountryWriteInput,
} from "./schemas";

function toQuery(filters: CountryFilters): QueryParams {
  return {
    search: filters.search || undefined,
    ordering: filters.ordering || undefined,
    page: filters.page && filters.page > 1 ? filters.page : undefined,
    page_size: filters.pageSize || undefined,
    has_properties: filters.hasProperties || undefined,
  };
}

export async function fetchCountries(filters: CountryFilters): Promise<Paginated<Country>> {
  const data = await apiGet<unknown>("/countries", { query: toQuery(filters) });
  return countriesListResponseSchema.parse(data);
}

export async function fetchCountry(iso2: string): Promise<Country> {
  const data = await apiGet<unknown>(`/countries/${iso2}`);
  return countrySchema.parse(data);
}

export async function createCountry(body: CountryWriteInput): Promise<Country> {
  const data = await apiSend<unknown>("POST", "/countries", body);
  return countrySchema.parse(data);
}

export async function updateCountry(
  iso2: string,
  body: Partial<CountryWriteInput>,
): Promise<Country> {
  const data = await apiSend<unknown>("PATCH", `/countries/${iso2}`, body);
  return countrySchema.parse(data);
}

export async function deleteCountry(iso2: string): Promise<void> {
  await apiSend<void>("DELETE", `/countries/${iso2}`);
}
