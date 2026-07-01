import { useAuthStore } from "@/features/auth/store";

// The wire role value is LOWERCASE (`core/enums.py` → "admin"/"reservations";
// the PermissionsView and auth store keep it verbatim), so compare
// case-insensitively — an uppercase-only set is effectively superuser-only in
// production (the latent bug `useHasAccountsRole` below already dodges).
const WRITER_ROLES = new Set(["admin", "reservations"]);

export function useHasReservationsRole(): boolean {
  return useAuthStore((s) => {
    if (s.isSuperuser) return true;
    return s.role != null && WRITER_ROLES.has(s.role.toLowerCase());
  });
}

// The wire role value is LOWERCASE (`core/enums.py` → "admin"/"accounts"; the
// PermissionsView and auth store both keep it verbatim). So this compares
// case-insensitively — NOT against an uppercase set like the reservations hook
// above, which is effectively superuser-only in production (a latent bug
// `useHasAdminRole` already dodges the same way). Gates the SD money actions
// (release / capture) per the IsAccountsWriter backend write gate.
const ACCOUNTS_WRITER_ROLES = new Set(["admin", "accounts"]);

export function useHasAccountsRole(): boolean {
  return useAuthStore((s) => {
    if (s.isSuperuser) return true;
    return s.role != null && ACCOUNTS_WRITER_ROLES.has(s.role.toLowerCase());
  });
}
