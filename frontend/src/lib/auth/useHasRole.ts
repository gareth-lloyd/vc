import { useAuthStore } from "@/features/auth/store";

const WRITER_ROLES = new Set(["ADMIN", "RESERVATIONS"]);

export function useHasReservationsRole(): boolean {
  return useAuthStore((s) => {
    if (s.isSuperuser) return true;
    return s.role != null && WRITER_ROLES.has(s.role);
  });
}
