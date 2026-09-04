// React Query hooks for the shared feature catalogue (BUG-019). Query keys
// stay central in lib/query/keys. Mutations (create/update/delete) live in
// features/admin/tags — only the list reads shared across features are here.
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { queryKeys } from "@/lib/query/keys";
import { fetchFeatureCategories, fetchFeatures } from "./api";
import type { FeatureCategoryFilters, FeatureFilters } from "./schemas";

export function useFeatureCategories(filters: FeatureCategoryFilters = {}) {
  return useQuery({
    queryKey: queryKeys.tagFeatureCategories.list(filters),
    queryFn: () => fetchFeatureCategories(filters),
    // Keeps the previous page's rows on screen while a page change refetches
    // (TagsAdminPage's admin table paginates this) instead of flashing the
    // DataTable to empty/loading between pages.
    placeholderData: keepPreviousData,
  });
}

export function useFeatures(filters: FeatureFilters = {}) {
  return useQuery({
    queryKey: queryKeys.tagFeatures.list(filters),
    queryFn: () => fetchFeatures(filters),
    placeholderData: keepPreviousData,
  });
}
