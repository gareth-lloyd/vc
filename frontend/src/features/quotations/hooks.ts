import { useQuery } from "@tanstack/react-query";
import { enabledQuery } from "@/lib/query/enabledQuery";
import { queryKeys, type QuotationId } from "@/lib/query/keys";
import { fetchQuotation, fetchQuotationLines, fetchQuotations } from "./api";
import type { QuotationFilters } from "./schemas";

export const QUOTATIONS_PAGE_SIZE = 50;

export function useQuotations(filters: QuotationFilters) {
  return useQuery({
    queryKey: queryKeys.quotations.list(filters),
    queryFn: () => fetchQuotations(filters),
  });
}

export function useQuotation(id: QuotationId | undefined) {
  return useQuery(enabledQuery(id, queryKeys.quotations.detail, fetchQuotation));
}

export function useQuotationLines(id: QuotationId | undefined) {
  return useQuery(enabledQuery(id, queryKeys.quotations.lines, fetchQuotationLines));
}
