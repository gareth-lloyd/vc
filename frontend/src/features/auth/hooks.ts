import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/lib/query/keys";
import { fetchMe, fetchPermissions, login, logout, verifyTfa } from "./api";
import { useAuthStore } from "./store";
import type { LoginInput, TfaVerifyInput } from "./schemas";

export function useMe() {
  return useQuery({
    queryKey: queryKeys.auth.me(),
    queryFn: async () => {
      const [user, permissions] = await Promise.all([fetchMe(), fetchPermissions()]);
      useAuthStore.getState().setMe(user, permissions);
      return { user, permissions };
    },
    retry: false,
    staleTime: 5 * 60_000,
  });
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: LoginInput) => login(input),
    onSuccess: async (data) => {
      if (data.tfa_required) {
        useAuthStore.getState().setPendingTfa({
          challengeToken: data.challenge_token,
          expiresAt: Date.now() + data.expires_in_seconds * 1000,
        });
        return;
      }
      await queryClient.invalidateQueries({ queryKey: queryKeys.auth.me() });
    },
  });
}

export function useVerifyTfa() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: TfaVerifyInput) => verifyTfa(input),
    onSuccess: async () => {
      useAuthStore.getState().setPendingTfa(null);
      await queryClient.invalidateQueries({ queryKey: queryKeys.auth.me() });
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => logout(),
    onSuccess: () => {
      useAuthStore.getState().clear();
      queryClient.removeQueries({ queryKey: queryKeys.auth.me() });
      queryClient.removeQueries({ queryKey: queryKeys.properties.all() });
      queryClient.removeQueries({ queryKey: queryKeys.bookings.all() });
    },
  });
}
