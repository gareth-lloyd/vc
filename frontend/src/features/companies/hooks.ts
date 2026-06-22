import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { queryKeys, type CompanyId } from "@/lib/query/keys";
import { enabledQuery } from "@/lib/query/enabledQuery";
import {
  createCompany,
  deleteCompany,
  fetchCompanies,
  fetchCompany,
  searchCompanies,
  updateCompany,
} from "./api";
import type { CompanyFilters, CompanyWriteInput } from "./schemas";

export function useCompanies(filters: CompanyFilters) {
  return useQuery({
    queryKey: queryKeys.companies.list(filters),
    queryFn: () => fetchCompanies(filters),
  });
}

export function useCompany(id: CompanyId | undefined) {
  return useQuery(enabledQuery(id, queryKeys.companies.detail, fetchCompany));
}

export function useSearchCompanies(query: string, opts?: { status?: string }) {
  return useQuery({
    queryKey: queryKeys.companies.search(query, opts?.status),
    queryFn: () => searchCompanies(query, opts),
    enabled: query.length >= 2,
  });
}

// A company's name/status/town surface on list rows, detail, AND the picker's
// search results — and `lists()`, `detail()` and `search()` are disjoint key
// prefixes. Invalidating the `all()` root catches all three, so no write leaves
// the directory list, a detail page, or a picker showing stale data.
function invalidateCompanies(queryClient: QueryClient) {
  queryClient.invalidateQueries({ queryKey: queryKeys.companies.all() });
}

export function useCreateCompany() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CompanyWriteInput) => createCompany(input),
    onSuccess: () => invalidateCompanies(queryClient),
  });
}

export function useUpdateCompany(companyId: CompanyId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: Partial<CompanyWriteInput>) => updateCompany(companyId, input),
    onSuccess: () => invalidateCompanies(queryClient),
  });
}

export function useDeleteCompany(companyId: CompanyId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => deleteCompany(companyId),
    onSuccess: () => invalidateCompanies(queryClient),
  });
}
