import { apiSend } from "@/lib/api/client";
import {
  featureCategorySchema,
  featureSchema,
  type Feature,
  type FeatureCategory,
  type FeatureCategoryWriteInput,
  type FeatureWriteInput,
} from "./schemas";

// The list reads now live in lib/domain/features (BUG-019, mirrors GAP-072);
// re-exported here for intra-feature (CRUD screen) callers.
export { fetchFeatureCategories, fetchFeatures, toFeaturesParam } from "@/lib/domain/features/api";

export async function createFeatureCategory(
  body: FeatureCategoryWriteInput,
): Promise<FeatureCategory> {
  const data = await apiSend<unknown>("POST", "/feature-categories", body);
  return featureCategorySchema.parse(data);
}

export async function updateFeatureCategory(
  id: number,
  body: Partial<FeatureCategoryWriteInput>,
): Promise<FeatureCategory> {
  const data = await apiSend<unknown>("PATCH", `/feature-categories/${id}`, body);
  return featureCategorySchema.parse(data);
}

export async function deleteFeatureCategory(id: number): Promise<void> {
  await apiSend<void>("DELETE", `/feature-categories/${id}`);
}

export async function createFeature(body: FeatureWriteInput): Promise<Feature> {
  const data = await apiSend<unknown>("POST", "/features", body);
  return featureSchema.parse(data);
}

export async function updateFeature(
  id: number,
  body: Partial<FeatureWriteInput>,
): Promise<Feature> {
  const data = await apiSend<unknown>("PATCH", `/features/${id}`, body);
  return featureSchema.parse(data);
}

export async function deleteFeature(id: number): Promise<void> {
  await apiSend<void>("DELETE", `/features/${id}`);
}
