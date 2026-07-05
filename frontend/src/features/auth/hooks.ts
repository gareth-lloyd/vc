import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/lib/query/keys";
import { runLogoutCleanups } from "@/lib/auth/logoutCleanup";
import {
  confirmPasswordReset,
  confirmTfaEnrollment,
  fetchMe,
  fetchPermissions,
  login,
  logout,
  requestPasswordReset,
  startTfaEnrollment,
  updateMe,
  verifyTfa,
} from "./api";
import { resetAuthQueryCache } from "./resetAuthQueryCache";
import { useAuthStore } from "./store";
import type { LoginInput, TfaVerifyInput, UserMe } from "./schemas";

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
      // Wipe any cache left by a previous session before the new user's data is
      // fetched, so one user is never served another's cached queries. The
      // subsequent `useMe` mount repopulates auth.me.
      resetAuthQueryCache(queryClient);
      // The login payload already carries the user, so flip the store to
      // "authenticated" now — otherwise status stays "idle" and the
      // redirect-after-login loses the race against the background `useMe`
      // refetch, forcing a second submit. `useMe` fills in permissions shortly.
      useAuthStore.getState().setMe(data.user);
    },
  });
}

export function useVerifyTfa() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: TfaVerifyInput) => verifyTfa(input),
    onSuccess: () => {
      useAuthStore.getState().setPendingTfa(null);
      resetAuthQueryCache(queryClient);
    },
  });
}

export function useStartTfaEnrollment() {
  return useMutation({
    mutationFn: () => startTfaEnrollment(),
  });
}

export function useConfirmTfaEnrollment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (code: string) => confirmTfaEnrollment(code),
    onSuccess: () => {
      // The user's tfa_method just changed NONE → totp. Flip the store first so
      // the boot proactive-redirect sees "totp" synchronously (a fast "continue"
      // click must not bounce back to /enroll-2fa), then wipe cached queries
      // (mirrors useVerifyTfa) so a fresh /auth/me repopulates from the server.
      useAuthStore.getState().markTfaEnrolled();
      resetAuthQueryCache(queryClient);
    },
  });
}

export function useUpdateMe() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: Partial<Pick<UserMe, "preferred_language">>) => updateMe(input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.auth.me() });
    },
  });
}

export function useRequestPasswordReset() {
  // Unauthenticated flow — no session is created, so no cache reset is needed.
  return useMutation({
    mutationFn: (email: string) => requestPasswordReset(email),
  });
}

export function useConfirmPasswordReset() {
  // Confirm returns 204 without logging in; the user signs in fresh at /login.
  return useMutation({
    mutationFn: (input: { token: string; new_password: string }) => confirmPasswordReset(input),
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => logout(),
    onSuccess: () => {
      useAuthStore.getState().clear();
      // Feature-owned session state (e.g. the owner-portal store) clears via
      // the registry — auth must not import other features (GAP-063).
      runLogoutCleanups();
      resetAuthQueryCache(queryClient);
    },
  });
}
