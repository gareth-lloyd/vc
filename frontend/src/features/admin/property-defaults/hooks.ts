import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/lib/query/keys";
import { fetchPropertyDefaults, updatePropertyDefaults } from "./api";
import type { PropertyDefaultsWriteInput } from "./schemas";

export function usePropertyDefaults() {
  return useQuery({
    queryKey: queryKeys.propertyDefaults.all(),
    queryFn: fetchPropertyDefaults,
  });
}

export function useUpdatePropertyDefaults() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: PropertyDefaultsWriteInput) => updatePropertyDefaults(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.propertyDefaults.all() });
    },
  });
}
