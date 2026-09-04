// Read-side fetchers for the shared feature catalogue (BUG-019). Feature
// WRITE paths (create/update/delete) stay in features/admin/tags — only the
// list reads that feed cross-feature consumers live here.
import { apiGet } from "@/lib/api/client";
import type { QueryParams } from "@/lib/api/url";
import type { Paginated } from "@/types/api";
import {
  featureCategoriesListResponseSchema,
  featuresListResponseSchema,
  type Feature,
  type FeatureCategory,
  type FeatureCategoryFilters,
  type FeatureFilters,
} from "./schemas";

// The ~300-row catalogue needs every row in one request for lookups
// (add-picker, detail chips) — the default page size of 50 would silently
// truncate it. Matches `ConfigurablePageSizePagination.max_page_size`.
export const FEATURE_CATALOGUE_PAGE_SIZE = 500;

function categoryQuery(filters: FeatureCategoryFilters): QueryParams {
  return {
    page: filters.page && filters.page > 1 ? filters.page : undefined,
    page_size: filters.pageSize,
  };
}

function featureQuery(filters: FeatureFilters): QueryParams {
  return {
    category: filters.category,
    page: filters.page && filters.page > 1 ? filters.page : undefined,
    page_size: filters.pageSize,
  };
}

export async function fetchFeatureCategories(
  filters: FeatureCategoryFilters = {},
): Promise<Paginated<FeatureCategory>> {
  const data = await apiGet<unknown>("/feature-categories", { query: categoryQuery(filters) });
  return featureCategoriesListResponseSchema.parse(data);
}

export async function fetchFeatures(filters: FeatureFilters = {}): Promise<Paginated<Feature>> {
  const data = await apiGet<unknown>("/features", { query: featureQuery(filters) });
  return featuresListResponseSchema.parse(data);
}

function normalizeFeatureSlugs(slugs: string[]): string[] {
  const seen = new Set<string>();
  for (const raw of slugs) {
    const slug = raw.trim();
    if (slug) seen.add(slug);
  }
  return [...seen];
}

// Comma-joined CSV, never an array. `buildQuery` (lib/api/url.ts) serializes
// a `string[]` QueryValue as REPEATED query keys (`?features=a&features=b`),
// but the backend's `PropertyFilter.filter_features` reads a single
// `request.GET.get("features")` — Django's `QueryDict.get` on a repeated key
// returns only the LAST value. Passing a raw array through would silently
// degrade the AND-filter to "only the last selected feature". Trims and
// dedupes so a hand-edited/bookmarked URL round-tripped through
// `fromFeaturesParam` can't smuggle whitespace or a duplicate slug into the
// query (whitespace would fail to match any real feature — see
// `fromFeaturesParam`'s docstring).
export function toFeaturesParam(slugs?: string[]): string | undefined {
  if (!slugs) return undefined;
  const normalized = normalizeFeatureSlugs(slugs);
  return normalized.length > 0 ? normalized.join(",") : undefined;
}

// The other half of the CSV contract `toFeaturesParam` owns — parses a
// `?features=` URL param back into slugs. Same single choke point so a
// hand-edited URL (`?features=pool, pool`) can't produce whitespace-mangled
// or duplicate slugs that would silently fail to match (whitespace) or
// collide on React key (duplicates) in `FeatureMultiSelect`.
export function fromFeaturesParam(param: string | null | undefined): string[] {
  if (!param) return [];
  return normalizeFeatureSlugs(param.split(","));
}
