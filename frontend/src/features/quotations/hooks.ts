import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { enabledQuery } from "@/lib/query/enabledQuery";
import { queryKeys, type QuotationId } from "@/lib/query/keys";
import {
  createGuest,
  createQuotation,
  createQuotationLine,
  fetchCurrentTermsVersion,
  fetchQuotation,
  fetchQuotationLines,
  fetchQuotations,
  searchQuoteOptions,
} from "./api";
import type {
  QuotationFilters,
  QuotationLineWriteInput,
  QuotationWriteInput,
  QuoteCriteriaInput,
} from "./schemas";

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

export function useCurrentTermsVersion() {
  return useQuery({
    queryKey: ["terms-versions", "current"] as const,
    queryFn: fetchCurrentTermsVersion,
    staleTime: 5 * 60 * 1000,
  });
}

// One-shot pricing search. Held as a mutation so the operator triggers
// it explicitly (and we don't refire on every re-render). Returns the
// priced options list.
export function useQuoteOptionsSearch() {
  return useMutation({
    mutationFn: ({ criteria, currency }: { criteria: QuoteCriteriaInput; currency: string }) =>
      searchQuoteOptions(criteria, currency),
  });
}

export function useCreateQuotation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createQuotation,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.quotations.all() });
    },
  });
}

export function useCreateQuotationLine(quotationId: QuotationId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: QuotationLineWriteInput) => createQuotationLine(quotationId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.quotations.lines(quotationId) });
      qc.invalidateQueries({ queryKey: queryKeys.quotations.detail(quotationId) });
    },
  });
}

export function useCreateGuest() {
  return useMutation({ mutationFn: createGuest });
}

// Convenience to compose multiple inputs into a single hook call.
export type CreateQuotationFromBuilderInput = {
  header: QuotationWriteInput;
  lines: QuotationLineWriteInput[];
};
