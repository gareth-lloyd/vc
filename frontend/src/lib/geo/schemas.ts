// Shared geo/taxonomy home (GAP-072). Regions, collections and countries are
// cross-cutting reference data consumed by properties, availability, clients,
// quotations and the shared Region/Country pickers — homing them here means
// any feature can read them without a feature→feature allowlist edge, and the
// shared pickers in src/components/form no longer reach into a feature.
// Old feature homes re-export these for intra-feature use; admin/countries
// keeps the country WRITE schema (CRUD is an admin concern).
import { z } from "zod";
import { paginated } from "@/lib/api/pagination";

// Minimal taxonomy rows for filter dropdowns (`GET /regions`, `/collections`).
export const regionSchema = z.object({
  id: z.number(),
  country: z.number().nullable().optional(),
  country_iso2: z.string().nullable().optional(),
  name: z.string(),
  slug: z.string(),
  is_active: z.boolean(),
});
export type Region = z.infer<typeof regionSchema>;

export const regionsResponseSchema = paginated(regionSchema);

export const collectionSchema = z.object({
  id: z.number(),
  name: z.string(),
  slug: z.string(),
});
export type Collection = z.infer<typeof collectionSchema>;

export const collectionsResponseSchema = paginated(collectionSchema);

export const countrySchema = z.object({
  id: z.number(),
  iso2: z.string(),
  name: z.string(),
  iso3: z.string().nullable().optional(),
  dial_code: z.string().nullable().optional(),
  default_tax_rate: z.union([z.string(), z.number()]).nullable().optional(),
  sort_order: z.number().optional().default(0),
  is_active: z.boolean(),
});
export type Country = z.infer<typeof countrySchema>;

export const countriesListResponseSchema = paginated(countrySchema);

export interface CountryFilters {
  search?: string;
  page?: number;
  ordering?: string;
  // Override the default page size — e.g. to load the full list into a
  // `<Select>` in one request. Capped server-side.
  pageSize?: number;
  // Only countries that actually hold properties (quote-builder criteria
  // dropdown); server-side opt-in narrowing, false behaves like absent.
  hasProperties?: boolean;
}

export interface RegionListFilters {
  // Only regions that actually hold properties (quote-builder criteria
  // dropdown); server-side opt-in narrowing, false behaves like absent.
  hasProperties?: boolean;
  // Scope to one country: `country` is the FK id, `countryIso2` the
  // case-insensitive ISO code — pass whichever the caller holds.
  country?: number;
  countryIso2?: string;
}
