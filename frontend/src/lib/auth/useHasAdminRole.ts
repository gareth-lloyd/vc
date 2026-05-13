import { useAuthStore } from "@/features/auth/store";

export function useHasAdminRole(): boolean {
  return useAuthStore((s) => {
    if (s.isSuperuser) return true;
    return s.role === "admin" || s.role === "ADMIN";
  });
}
