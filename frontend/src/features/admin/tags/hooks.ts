import { useMutation, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/lib/query/keys";
import {
  createFeature,
  createFeatureCategory,
  deleteFeature,
  deleteFeatureCategory,
  updateFeature,
  updateFeatureCategory,
} from "./api";
import type { FeatureCategoryWriteInput, FeatureWriteInput } from "./schemas";

// The list-read hooks now live in lib/domain/features (BUG-019, mirrors
// GAP-072); re-exported here for intra-feature (CRUD screen) callers.
export { useFeatureCategories, useFeatures } from "@/lib/domain/features/hooks";

export function useCreateFeatureCategory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: FeatureCategoryWriteInput) => createFeatureCategory(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.tagFeatureCategories.lists() });
    },
  });
}

export function useUpdateFeatureCategory(id: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: Partial<FeatureCategoryWriteInput>) => updateFeatureCategory(id, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.tagFeatureCategories.lists() });
    },
  });
}

export function useDeleteFeatureCategory(id: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => deleteFeatureCategory(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.tagFeatureCategories.lists() });
    },
  });
}

export function useCreateFeature() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: FeatureWriteInput) => createFeature(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.tagFeatures.lists() });
    },
  });
}

export function useUpdateFeature(id: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: Partial<FeatureWriteInput>) => updateFeature(id, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.tagFeatures.lists() });
    },
  });
}

export function useDeleteFeature(id: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => deleteFeature(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.tagFeatures.lists() });
    },
  });
}
