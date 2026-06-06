import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/lib/query/keys";
import {
  contestOwnerBlockUpdate,
  fetchOwnerBlockUpdates,
  markOwnerBlockUpdateSeen,
  markOwnerBlockUpdateUnseen,
} from "./api";
import type { OwnerBlockUpdateFilters } from "./schemas";

// The whole feed reorders (unseen-first) when any row's seen/contested state
// changes, so mutations invalidate the feed prefix rather than a single key.
const OWNER_BLOCK_UPDATES_KEY = queryKeys.ownerBlockUpdates.all();

export function useOwnerBlockUpdates(filters: OwnerBlockUpdateFilters) {
  return useQuery({
    queryKey: queryKeys.ownerBlockUpdates.list(filters),
    queryFn: () => fetchOwnerBlockUpdates(filters),
    retry: false,
  });
}

export function useMarkSeen() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => markOwnerBlockUpdateSeen(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: OWNER_BLOCK_UPDATES_KEY });
    },
  });
}

export function useMarkUnseen() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => markOwnerBlockUpdateUnseen(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: OWNER_BLOCK_UPDATES_KEY });
    },
  });
}

export function useContestBlock() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) =>
      contestOwnerBlockUpdate(id, reason),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: OWNER_BLOCK_UPDATES_KEY });
    },
  });
}
