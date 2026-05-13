import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { enabledQuery } from "@/lib/query/enabledQuery";
import { queryKeys, type QuotationId } from "@/lib/query/keys";
import {
  createGuest,
  createQuotation,
  createQuotationLine,
  deleteQuotationLine,
  duplicateQuotation,
  fetchCurrentTermsVersion,
  fetchQuotation,
  fetchQuotationLines,
  fetchQuotations,
  searchQuoteOptions,
  sendQuotation,
  updateQuotationLine,
  withdrawQuotation,
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

// ----------------------------------------------------------------------
// Lifecycle action hooks — send / duplicate / withdraw.
// ----------------------------------------------------------------------

function invalidateQuotation(qc: ReturnType<typeof useQueryClient>, id: QuotationId) {
  qc.invalidateQueries({ queryKey: queryKeys.quotations.detail(id) });
  qc.invalidateQueries({ queryKey: queryKeys.quotations.lines(id) });
  qc.invalidateQueries({ queryKey: queryKeys.quotations.lists() });
}

export function useSendQuotation(id: QuotationId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => sendQuotation(id),
    onSuccess: (quotation) => {
      invalidateQuotation(qc, id);
      // Parent enquiry status flips to QUOTED — refresh that view too.
      if (quotation.enquiry != null) {
        qc.invalidateQueries({ queryKey: queryKeys.enquiries.detail(quotation.enquiry) });
        qc.invalidateQueries({ queryKey: queryKeys.enquiries.activity(quotation.enquiry) });
      }
    },
  });
}

export function useDuplicateQuotation(id: QuotationId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => duplicateQuotation(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.quotations.lists() });
    },
  });
}

export function useWithdrawQuotation(id: QuotationId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (reason: string) => withdrawQuotation(id, reason),
    onSuccess: () => invalidateQuotation(qc, id),
  });
}

// ----------------------------------------------------------------------
// Line CRUD hooks — update / delete a single line.
// (Create is already covered by `useCreateQuotationLine` / `SaveQuoteDialog`.)
// ----------------------------------------------------------------------

export function useUpdateQuotationLine(quotationId: QuotationId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ lineId, body }: { lineId: number; body: Partial<QuotationLineWriteInput> }) =>
      updateQuotationLine(quotationId, lineId, body),
    onSuccess: () => invalidateQuotation(qc, quotationId),
  });
}

export function useDeleteQuotationLine(quotationId: QuotationId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (lineId: number) => deleteQuotationLine(quotationId, lineId),
    onSuccess: () => invalidateQuotation(qc, quotationId),
  });
}
