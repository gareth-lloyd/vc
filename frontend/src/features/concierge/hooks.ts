import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/lib/query/keys";
import { fetchConciergeOverview, setServiceStatus } from "./api";

export function useConciergeOverview() {
  return useQuery({
    queryKey: queryKeys.concierge.overview(),
    queryFn: fetchConciergeOverview,
  });
}

export function useSetServiceStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: setServiceStatus,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.concierge.all() });
    },
  });
}
