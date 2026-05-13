import { useQuery } from "@tanstack/react-query";
import { queryKeys } from "@/lib/query/keys";
import { fetchAuditLog } from "./api";
import type { AuditLogFilters } from "./schemas";

export function useAuditLog(filters: AuditLogFilters) {
  return useQuery({
    queryKey: queryKeys.audit.list(filters),
    queryFn: () => fetchAuditLog(filters),
    retry: false,
  });
}
