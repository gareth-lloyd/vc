import { useQuery } from "@tanstack/react-query";
import { queryKeys } from "@/lib/query/keys";
import { fetchClients } from "./api";
import type { ClientFilters } from "./schemas";

export function useClients(filters: ClientFilters) {
  return useQuery({
    queryKey: queryKeys.clients.list(filters),
    queryFn: () => fetchClients(filters),
  });
}
