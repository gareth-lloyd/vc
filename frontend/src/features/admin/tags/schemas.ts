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

export const featureCategoryWriteInputSchema = z.object({
  name: z.string().trim().min(1).max(128),
  slug: z.string().trim().min(1).max(128),
  description: z.string().trim().max(2000).optional(),
  icon: z.string().trim().max(128).optional(),
  sort_order: z.number().int().min(0).optional(),
  is_active: z.boolean().optional(),
});
export type FeatureCategoryWriteInput = z.infer<typeof featureCategoryWriteInputSchema>;

export const featureWriteInputSchema = z.object({
  category: z.number().int(),
  name: z.string().trim().min(1).max(128),
  slug: z.string().trim().min(1).max(128),
  description: z.string().trim().max(2000).optional(),
  icon: z.string().trim().max(128).optional(),
  sort_order: z.number().int().min(0).optional(),
  is_active: z.boolean().optional(),
  service_type: featureServiceTypeSchema.optional(),
});
export type FeatureWriteInput = z.infer<typeof featureWriteInputSchema>;

export interface FeatureFilters {
  category?: number;
  page?: number;
}

export interface FeatureCategoryFilters {
  page?: number;
}

export const featureCategoryQueryKeys = {
  all: () => ["feature-categories"] as const,
  lists: () => ["feature-categories", "list"] as const,
  list: <F>(filters: F) => ["feature-categories", "list", filters] as const,
  detail: (id: number | string) => ["feature-categories", "detail", id] as const,
};

export const featureQueryKeys = {
  all: () => ["features"] as const,
  lists: () => ["features", "list"] as const,
  list: <F>(filters: F) => ["features", "list", filters] as const,
  detail: (id: number | string) => ["features", "detail", id] as const,
};
