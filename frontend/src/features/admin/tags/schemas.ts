import { z } from "zod";
import { featureServiceTypeSchema } from "@/lib/domain/features/schemas";

// The feature READ shapes now live in lib/domain/features (BUG-019, mirrors
// GAP-072) so any feature can read them without a properties/admin edge;
// re-exported here for intra-feature consumers. The WRITE schemas stay here —
// feature/category CRUD is an admin-only concern.
export {
  featureCategoriesListResponseSchema,
  featureCategorySchema,
  featureSchema,
  featureServiceTypeSchema,
  featuresListResponseSchema,
  FEATURE_SERVICE_TYPES,
  type Feature,
  type FeatureCategory,
  type FeatureCategoryFilters,
  type FeatureFilters,
  type FeatureServiceType,
} from "@/lib/domain/features/schemas";

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
