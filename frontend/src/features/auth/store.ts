import { create } from "zustand";
import type { PermissionsResponse, UserMe } from "./schemas";

type AuthStatus = "idle" | "authenticated" | "unauthenticated";

interface PendingTfa {
  challengeToken: string;
  expiresAt: number;
}

interface AuthState {
  user: UserMe | null;
  permissions: string[];
  role: string | null;
  isSuperuser: boolean;
  status: AuthStatus;
  pendingTfa: PendingTfa | null;
  setMe: (user: UserMe, perms?: PermissionsResponse | null) => void;
  setUnauthenticated: () => void;
  clear: () => void;
  setPendingTfa: (pending: PendingTfa | null) => void;
  markTfaEnrolled: () => void;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  permissions: [],
  role: null,
  isSuperuser: false,
  status: "idle",
  pendingTfa: null,
  setMe: (user, perms = null) =>
    set({
      user,
      role: perms?.role ?? user.role ?? null,
      isSuperuser: perms?.is_superuser ?? user.is_superuser,
      permissions: perms?.permissions ?? [],
      status: "authenticated",
    }),
  setUnauthenticated: () => {
    if (get().status === "unauthenticated") return;
    set({
      user: null,
      permissions: [],
      role: null,
      isSuperuser: false,
      status: "unauthenticated",
    });
  },
  clear: () =>
    set({
      user: null,
      permissions: [],
      role: null,
      isSuperuser: false,
      status: "unauthenticated",
      pendingTfa: null,
    }),
  setPendingTfa: (pending) => set({ pendingTfa: pending }),
  // Optimistically flip tfa_method after a successful enrolment confirm so the
  // boot proactive-redirect (which reads the store) sees "totp" immediately and
  // doesn't bounce the user back to /enroll-2fa before /auth/me refetches.
  markTfaEnrolled: () => set((s) => (s.user ? { user: { ...s.user, tfa_method: "totp" } } : {})),
}));
