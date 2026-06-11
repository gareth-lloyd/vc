import { z } from "zod";
import { paginated } from "@/lib/api/pagination";

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

export const countryWriteInputSchema = z.object({
  iso2: z.string().trim().min(2).max(2),
  name: z.string().trim().min(1).max(120),
  iso3: z.string().trim().max(3).optional(),
  dial_code: z.string().trim().max(8).optional(),
  default_tax_rate: z.string().optional(),
  sort_order: z.number().int().min(0).optional(),
  is_active: z.boolean().optional(),
});
export type CountryWriteInput = z.infer<typeof countryWriteInputSchema>;

export interface CountryFilters {
  search?: string;
  page?: number;
  ordering?: string;
  // Override the default page size — e.g. to load the full list into a
  // `<Select>` in one request. Capped server-side.
  pageSize?: number;
}
