import { z } from "zod";

// The country READ shapes now live in lib/geo (GAP-072) so any feature can
// read them without a properties/admin edge; re-exported here for intra-feature
// consumers. The WRITE schema stays — country CRUD is an admin-only concern.
export {
  countrySchema,
  countriesListResponseSchema,
  type Country,
  type CountryFilters,
} from "@/lib/geo/schemas";

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
