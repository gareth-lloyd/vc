import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/lib/query/keys";
import {
  createFeature,
  createFeatureCategory,
  deleteFeature,
  deleteFeatureCategory,
  fetchFeatureCategories,
  fetchFeatures,
  updateFeature,
  updateFeatureCategory,
} from "./api";
import type {
  FeatureCategoryFilters,
  FeatureCategoryWriteInput,
  FeatureFilters,
  FeatureWriteInput,
} from "./schemas";

export function useFeatureCategories(filters: FeatureCategoryFilters) {
  return useQuery({
    queryKey: queryKeys.tagFeatureCategories.list(filters),
    queryFn: () => fetchFeatureCategories(filters),
  });
}

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

export function useFeatures(filters: FeatureFilters) {
  return useQuery({
    queryKey: queryKeys.tagFeatures.list(filters),
    queryFn: () => fetchFeatures(filters),
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
