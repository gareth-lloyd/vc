import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { enabledQuery } from "@/lib/query/enabledQuery";
import { queryKeys, type QuotationId } from "@/lib/query/keys";
import {
  invalidateBookingDependents,
  invalidatePropertyAvailability,
  invalidateQuotationDependents,
  invalidateQuotationRelated,
} from "@/lib/query/invalidate";
import { fetchStatusCounts } from "@/lib/api/statusCounts";
import {
  convertQuotation,
  createQuotation,
  deleteQuotationLine,
  duplicateQuotation,
  fetchCurrentTermsVersion,
  fetchQuotation,
  fetchQuotationLines,
  fetchQuotationPreview,
  fetchQuotations,
  holdQuotationLine,
  quotationStatusCountsQuery,
  markQuotationManuallySent,
  releaseQuotationLineHold,
  repriceStayOption,
  searchQuoteOptions,
  sendQuotation,
  updateQuotationLine,
  withdrawQuotation,
  type ConvertQuotationInput,
} from "./api";
import type {
  QuotationDetail,
  QuotationFilters,
  QuotationLine,
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

// Reprices one picked stay block (StayOptionPicker). A plain mutation — the
// picker caches per-block results in row-local state, so no query cache.
export function useRepriceStayOption() {
  return useMutation({ mutationFn: repriceStayOption });
}

export function useCreateQuotation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createQuotation,
    // The new draft shifts the list + badge counts and appears on the parent
    // enquiry and the guest/agent contact rails (BUG-018).
    onSuccess: (created) => invalidateQuotationDependents(qc, created),
  });
}

// ----------------------------------------------------------------------
// Lifecycle action hooks — send / duplicate / withdraw / convert. All route
// through invalidateQuotationDependents: every response is the (new)
// QuotationDetail, which carries the enquiry/guest/agent FKs the cross-entity
// surfaces hang off.
// ----------------------------------------------------------------------

function invalidateQuotationLines(qc: ReturnType<typeof useQueryClient>, id: QuotationId) {
  // Line CRUD changes totals on detail but not on the list row. detail(id)
  // is a prefix of the lines/preview sub-keys, so one call covers them all.
  qc.invalidateQueries({ queryKey: queryKeys.quotations.detail(id) });
}

// Path A — sends the guest email. Optional overrides (subject/intro/signoff)
// flow into the email; no-arg callers keep working.
export function useSendQuotation(id: QuotationId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (overrides?: QuotationSendOverrides) => sendQuotation(id, overrides),
    onSuccess: (quotation) => invalidateQuotationDependents(qc, quotation),
  });
}

// Path B — records SENT without dispatching email (copy-to-clipboard flow).
export function useMarkQuotationManuallySent(id: QuotationId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => markQuotationManuallySent(id),
    onSuccess: (quotation) => invalidateQuotationDependents(qc, quotation),
  });
}

export function useDuplicateQuotation(id: QuotationId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => duplicateQuotation(id),
    // The response is the NEW draft — same enquiry/contacts, new id.
    onSuccess: (duplicated) => invalidateQuotationDependents(qc, duplicated),
  });
}

export function useWithdrawQuotation(id: QuotationId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (reason: string) => withdrawQuotation(id, reason),
    onSuccess: (quotation) => invalidateQuotationDependents(qc, quotation),
  });
}

export function useConvertQuotation(
  quotation: Pick<QuotationDetail, "id" | "enquiry" | "guest" | "agent">,
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: ConvertQuotationInput) => convertQuotation(quotation.id, input),
    onSuccess: (booking) => {
      // The quotation flips to ACCEPTED, its parent enquiry to CONVERTED, and
      // a new booking appears whose dates block the villa.
      invalidateQuotationDependents(qc, quotation);
      qc.setQueryData(queryKeys.bookings.detail(booking.id), booking);
      invalidateBookingDependents(qc, booking);
    },
  });
}

// Line CRUD hooks. Create has no hook: new lines ride nested on the atomic
// `POST /quotations` body (`SaveQuoteDialog`); these edit existing lines.
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

// Related-entity FKs threaded from the caller's QuotationDetail — a hold
// isn't a status transition, so hold hooks refresh the related surfaces
// without churning quotation lists/status counts.
type QuotationRelated = { enquiry?: number | null; guest?: number | null; agent?: number | null };

// Manual hold toggles. A hold blocks the villa's dates for everyone, so the
// held line's property availability (calendar grid, holds, multi-villa
// timeline) restains, plus the parent enquiry / contact rails.
function invalidateAfterHoldChange(
  qc: ReturnType<typeof useQueryClient>,
  id: QuotationId,
  line: QuotationLine,
  related: QuotationRelated,
) {
  invalidateQuotationLines(qc, id);
  if (line.property != null) {
    invalidatePropertyAvailability(qc, line.property);
  } else {
    qc.invalidateQueries({ queryKey: queryKeys.availability.all() });
  }
  invalidateQuotationRelated(qc, related);
}

// `related` is required (though possibly undefined while the quotation is
// still loading) so call sites can't silently forget to thread it: undefined
// degrades to a broad contacts refresh and no enquiry refresh.
export function useHoldQuotationLine(
  quotationId: QuotationId,
  related: QuotationRelated | undefined,
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (lineId: number) => holdQuotationLine(quotationId, lineId),
    onSuccess: (line) => invalidateAfterHoldChange(qc, quotationId, line, related ?? {}),
  });
}

export function useReleaseQuotationLineHold(
  quotationId: QuotationId,
  related: QuotationRelated | undefined,
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (lineId: number) => releaseQuotationLineHold(quotationId, lineId),
    onSuccess: (line) => invalidateAfterHoldChange(qc, quotationId, line, related ?? {}),
  });
}
