import { apiGet, apiSend } from "@/lib/api/client";
import type { QueryParams } from "@/lib/api/url";
import type { Paginated } from "@/types/api";
import {
  featureCategoriesListResponseSchema,
  featureCategorySchema,
  featureSchema,
  featuresListResponseSchema,
  type Feature,
  type FeatureCategory,
  type FeatureCategoryFilters,
  type FeatureCategoryWriteInput,
  type FeatureFilters,
  type FeatureWriteInput,
} from "./schemas";

function categoryQuery(filters: FeatureCategoryFilters): QueryParams {
  return {
    page: filters.page && filters.page > 1 ? filters.page : undefined,
  };
}

function featureQuery(filters: FeatureFilters): QueryParams {
  return {
    category: filters.category,
    page: filters.page && filters.page > 1 ? filters.page : undefined,
  };
}

export async function fetchFeatureCategories(
  filters: FeatureCategoryFilters,
): Promise<Paginated<FeatureCategory>> {
  const data = await apiGet<unknown>("/feature-categories", { query: categoryQuery(filters) });
  return featureCategoriesListResponseSchema.parse(data);
}

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

export async function fetchFeatures(filters: FeatureFilters): Promise<Paginated<Feature>> {
  const data = await apiGet<unknown>("/features", { query: featureQuery(filters) });
  return featuresListResponseSchema.parse(data);
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
