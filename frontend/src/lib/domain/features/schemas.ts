// Shared feature/amenity read-side home (BUG-019, mirrors GAP-072 lib/geo).
// Features (pool, sea view, aircon, ...) are cross-cutting reference data
// read by properties (detail tabs) and quotations (candidate search) — homing
// the read side here means either feature can consume it without a new
// feature→feature allowlist edge (frontend/CLAUDE.md bans adding one for a
// new need). Feature CRUD (create/update/delete + write schemas) stays in
// features/admin/tags/ — editing the catalog is an admin concern. The old
// admin/tags home re-exports these for intra-feature use.
import { z } from "zod";
import { paginated } from "@/lib/api/pagination";

export const featureServiceTypeSchema = z.enum(["amenity", "included_service", "paid_addon"]);
export type FeatureServiceType = z.infer<typeof featureServiceTypeSchema>;
export const FEATURE_SERVICE_TYPES: FeatureServiceType[] = [
  "amenity",
  "included_service",
  "paid_addon",
];

export const featureCategorySchema = z.object({
  id: z.number(),
  name: z.string(),
  slug: z.string(),
  description: z.string().nullable().optional().default(""),
  icon: z.string().nullable().optional().default(""),
  sort_order: z.number().optional().default(0),
  is_active: z.boolean(),
});
export type FeatureCategory = z.infer<typeof featureCategorySchema>;

export const featureSchema = z.object({
  id: z.number(),
  category: z.number(),
  name: z.string(),
  slug: z.string(),
  description: z.string().nullable().optional().default(""),
  icon: z.string().nullable().optional().default(""),
  sort_order: z.number().optional().default(0),
  is_active: z.boolean(),
  service_type: z.string().default("amenity"),
});
export type Feature = z.infer<typeof featureSchema>;

export const featureCategoriesListResponseSchema = paginated(featureCategorySchema);
export const featuresListResponseSchema = paginated(featureSchema);

export interface FeatureFilters {
  category?: number;
  page?: number;
  pageSize?: number;
}

export interface FeatureCategoryFilters {
  page?: number;
  pageSize?: number;
}
