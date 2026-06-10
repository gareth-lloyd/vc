import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { enabledQuery } from "@/lib/query/enabledQuery";
import { queryKeys, type QuotationId } from "@/lib/query/keys";
import { fetchStatusCounts } from "@/lib/api/statusCounts";
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
  quotationStatusCountsQuery,
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

export function useQuotationStatusCounts(filters: QuotationFilters) {
  const query = quotationStatusCountsQuery(filters);
  return useQuery({
    queryKey: queryKeys.quotations.statusCounts(query),
    queryFn: () => fetchStatusCounts("/quotations/status-counts", query),
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

// One-page pricing search. Held as a mutation so the operator triggers
// it explicitly (and we don't refire on every re-render). Returns one page
// of priced options; the builder accumulates pages as the operator loads more.
export function useQuoteOptionsSearch() {
  return useMutation({
    mutationFn: ({ criteria, page }: { criteria: QuoteCriteriaInput; page: number }) =>
      searchQuoteOptions(criteria, page),
  });
}

export function useCreateQuotation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createQuotation,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.quotations.lists() });
      // A new draft row shifts the status tab-bar badge counts.
      qc.invalidateQueries({ queryKey: queryKeys.quotations.statusCountsAll() });
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
  // The status tab-bar badges count by status, so any transition restains them.
  qc.invalidateQueries({ queryKey: queryKeys.quotations.statusCountsAll() });
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
      // The duplicate is a new draft row, shifting the status tab-bar badges.
      qc.invalidateQueries({ queryKey: queryKeys.quotations.statusCountsAll() });
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
      // refresh both feature lists + the new booking detail + both badge sets.
      invalidateQuotationStatus(qc, id);
      qc.invalidateQueries({ queryKey: queryKeys.bookings.lists() });
      qc.invalidateQueries({ queryKey: queryKeys.bookings.statusCountsAll() });
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
