import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/lib/query/keys";
import { fetchSystemSettings, updateSystemSettings } from "./api";
import type { SystemSettingsWriteInput } from "./schemas";

export function useSystemSettings() {
  return useQuery({
    queryKey: queryKeys.systemSettings.all(),
    queryFn: fetchSystemSettings,
  });
}

export function useUpdateSystemSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: SystemSettingsWriteInput) => updateSystemSettings(input),
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.systemSettings.all(), data);
    },
  });
}
