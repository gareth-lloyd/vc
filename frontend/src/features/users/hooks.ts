import { useQuery } from "@tanstack/react-query";
import { queryKeys } from "@/lib/query/keys";
import { fetchUsers } from "./api";
import type { UserFilters } from "./schemas";

export function useUsers(filters: UserFilters) {
  return useQuery({
    queryKey: queryKeys.users.list(filters),
    queryFn: () => fetchUsers(filters),
  });
}
