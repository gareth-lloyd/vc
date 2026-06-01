import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { enabledQuery } from "@/lib/query/enabledQuery";
import { queryKeys, type QuotationId } from "@/lib/query/keys";
import {
  convertQuotation,
  createGuest,
  createQuotation,
  deleteQuotationLine,
  duplicateQuotation,
  fetchCurrentTermsVersion,
  fetchQuotation,
  fetchQuotationLines,
  fetchQuotationPreview,
  fetchQuotations,
  markQuotationManuallySent,
  searchQuoteOptions,
  sendQuotation,
  updateQuotationLine,
  withdrawQuotation,
  type ConvertQuotationInput,
} from "./api";
import type {
  QuotationDetail,
  QuotationFilters,
  QuotationLineWriteInput,
  QuotationSendOverrides,
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

// TODO: lines fetch sees only DRF's default first page (PAGE_SIZE=50); the
// default paginator has no page_size_query_param so clients can't override.
// Real quotes are 1-5 lines so the ceiling is comfortably above realistic
// usage, but a >50-line quote would silently truncate the convert dialog
// and the lines table. Wire a paginator that exposes `page_size` when a
// real quote ever pushes the cap.
export function useQuotationLines(id: QuotationId | undefined) {
  return useQuery(enabledQuery(id, queryKeys.quotations.lines, fetchQuotationLines));
}

// Guest-facing preview. Read-only and only fired while the send/copy flow
// is active — the caller passes `enabled` so we don't fetch for every
// closed dialog in a list. Optional `overrides` (subject/intro/signoff)
// flow into both the request and the query key, so the cached html
// re-fetches whenever the operator's edits change.
export function useQuotationPreview(
  id: QuotationId,
  enabled: boolean,
  overrides?: Partial<QuotationSendOverrides>,
) {
  return useQuery({
    queryKey: queryKeys.quotations.preview(id, overrides),
    queryFn: () => fetchQuotationPreview(id, overrides),
    enabled,
    // Keep the last rendered preview on screen while an override refetch is in
    // flight, so the iframe / form don't flicker back to skeleton on each edit.
    placeholderData: keepPreviousData,
  });
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
      qc.invalidateQueries({ queryKey: queryKeys.quotations.lists() });
    },
  });
}

export function useCreateGuest() {
  return useMutation({ mutationFn: createGuest });
}

// ----------------------------------------------------------------------
// Lifecycle action hooks — send / duplicate / withdraw.
// ----------------------------------------------------------------------

function invalidateQuotationStatus(qc: ReturnType<typeof useQueryClient>, id: QuotationId) {
  // Lifecycle actions can change the row visible on the list (status, etc.).
  qc.invalidateQueries({ queryKey: queryKeys.quotations.detail(id) });
  qc.invalidateQueries({ queryKey: queryKeys.quotations.lists() });
}

function invalidateQuotationLines(qc: ReturnType<typeof useQueryClient>, id: QuotationId) {
  // Line CRUD changes totals on detail but not on the list row.
  qc.invalidateQueries({ queryKey: queryKeys.quotations.lines(id) });
  qc.invalidateQueries({ queryKey: queryKeys.quotations.detail(id) });
}

function invalidateAfterSend(
  qc: ReturnType<typeof useQueryClient>,
  id: QuotationId,
  quotation: QuotationDetail,
) {
  invalidateQuotationStatus(qc, id);
  // Parent enquiry status flips to QUOTED — refresh that view too.
  if (quotation.enquiry != null) {
    qc.invalidateQueries({ queryKey: queryKeys.enquiries.detail(quotation.enquiry) });
    qc.invalidateQueries({ queryKey: queryKeys.enquiries.activity(quotation.enquiry) });
  }
}

// Path A — sends the guest email. Optional overrides (subject/intro/signoff)
// flow into the email; no-arg callers keep working.
export function useSendQuotation(id: QuotationId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (overrides?: QuotationSendOverrides) => sendQuotation(id, overrides),
    onSuccess: (quotation) => invalidateAfterSend(qc, id, quotation),
  });
}

// Path B — records SENT without dispatching email (copy-to-clipboard flow).
export function useMarkQuotationManuallySent(id: QuotationId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => markQuotationManuallySent(id),
    onSuccess: (quotation) => invalidateAfterSend(qc, id, quotation),
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
    onSuccess: () => invalidateQuotationStatus(qc, id),
  });
}

export function useConvertQuotation(id: QuotationId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: ConvertQuotationInput) => convertQuotation(id, input),
    onSuccess: (booking) => {
      // The quotation flips to ACCEPTED and a new booking row appears —
      // refresh both feature lists + the new booking detail.
      invalidateQuotationStatus(qc, id);
      qc.invalidateQueries({ queryKey: queryKeys.bookings.lists() });
      qc.invalidateQueries({ queryKey: queryKeys.bookings.detail(booking.id) });
    },
  });
}

// Line CRUD hooks. Create lives in `SaveQuoteDialog`, which fans the
// requests out in parallel and invalidates once at the end.
export function useUpdateQuotationLine(quotationId: QuotationId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ lineId, body }: { lineId: number; body: Partial<QuotationLineWriteInput> }) =>
      updateQuotationLine(quotationId, lineId, body),
    onSuccess: () => invalidateQuotationLines(qc, quotationId),
  });
}

export function useDeleteQuotationLine(quotationId: QuotationId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (lineId: number) => deleteQuotationLine(quotationId, lineId),
    onSuccess: () => invalidateQuotationLines(qc, quotationId),
  });
}
