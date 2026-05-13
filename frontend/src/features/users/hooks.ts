import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys, type UserId } from "@/lib/query/keys";
import { enabledQuery } from "@/lib/query/enabledQuery";
import {
  activateUser,
  createUser,
  deactivateUser,
  fetchUser,
  fetchUsers,
  reset2fa,
  updateUser,
} from "./api";
import type { UserCreateInput, UserFilters, UserUpdateInput } from "./schemas";

export function useUsers(filters: UserFilters) {
  return useQuery({
    queryKey: queryKeys.users.list(filters),
    queryFn: () => fetchUsers(filters),
  });
}

export function useUser(id: UserId | undefined) {
  return useQuery(enabledQuery(id, queryKeys.users.detail, fetchUser));
}

export function useCreateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: UserCreateInput) => createUser(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.users.lists() });
    },
  });
}

export function useUpdateUser(id: UserId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: Partial<UserUpdateInput>) => updateUser(id, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.users.lists() });
      queryClient.invalidateQueries({ queryKey: queryKeys.users.detail(id) });
    },
  });
}

export function useDeactivateUser(id: UserId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => deactivateUser(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.users.lists() });
      queryClient.invalidateQueries({ queryKey: queryKeys.users.detail(id) });
    },
  });
}

export function useActivateUser(id: UserId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => activateUser(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.users.lists() });
      queryClient.invalidateQueries({ queryKey: queryKeys.users.detail(id) });
    },
  });
}

export function useReset2fa(id: UserId) {
  return useMutation({
    mutationFn: () => reset2fa(id),
  });
}
