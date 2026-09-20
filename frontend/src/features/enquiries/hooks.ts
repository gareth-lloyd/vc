import {
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
  type QueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";
import { queryKeys, type EnquiryId } from "@/lib/query/keys";
import { invalidateEnquiryDependents, invalidateQuotationDependents } from "@/lib/query/invalidate";
import { enabledQuery } from "@/lib/query/enabledQuery";
import { fetchStatusCounts } from "@/lib/api/statusCounts";
import {
  assignEnquiry,
  closeEnquiry,
  convertEnquiry,
  createEnquiry,
  createEnquiryNote,
  enquiryStatusCountsQuery,
  fetchEnquiries,
  fetchEnquiry,
  fetchEnquiryActivity,
  fetchEnquiryNotes,
  reopenEnquiry,
  setEnquiryLeadStatus,
  updateEnquiry,
} from "./api";
import { KANBAN_STATUSES } from "./schemas";
import type {
  AssignEnquiryInput,
  CloseEnquiryInput,
  EnquiryDetail,
  EnquiryFilters,
  EnquiryListItem,
  EnquiryNoteWriteInput,
  EnquiryStatus,
  EnquiryWriteInput,
} from "./schemas";
import type { Paginated } from "@/types/api";
import type { LeadStatus } from "@/styles/tokens";

export const ENQUIRIES_PAGE_SIZE = 50;

/**
 * GAP-118: how many cards a Kanban column shows. The board is a triage
 * surface, not a browser — the column badge carries the true total and the
 * footer links to the filtered list for the rest.
 */
export const KANBAN_COLUMN_PAGE_SIZE = 20;

export function useEnquiries(filters: EnquiryFilters, { enabled = true } = {}) {
  return useQuery({
    queryKey: queryKeys.enquiries.list(filters),
    queryFn: () => fetchEnquiries(filters),
    // GAP-118: the board no longer rides this query. Hooks cannot be
    // conditional, so without the flag the list request would still fire
    // alongside the per-column fan-out on every board render.
    enabled,
  });
}

interface KanbanColumnsResult {
  byStatus: Partial<Record<EnquiryStatus, Paginated<EnquiryListItem>>>;
  /** The columns whose own request failed — the rest still render. */
  failed: EnquiryStatus[];
  isLoading: boolean;
  isError: boolean;
  isFetching: boolean;
  error: unknown;
  refetch: () => void;
}

function combineKanbanColumns(
  results: UseQueryResult<Paginated<EnquiryListItem>>[],
): KanbanColumnsResult {
  const byStatus: Partial<Record<EnquiryStatus, Paginated<EnquiryListItem>>> = {};
  const failed: EnquiryStatus[] = [];
  KANBAN_STATUSES.forEach((status, i) => {
    const page = results[i]?.data;
    if (page) byStatus[status] = page;
    if (results[i]?.isError) failed.push(status);
  });
  return {
    byStatus,
    failed,
    isLoading: results.some((r) => r.isLoading),
    // Board-wide failure ONLY when nothing loaded. The board went from one
    // request to one per column, so `some` would let a single transient 500
    // replace two perfectly good lanes with a full-width error; a failed lane
    // reports itself through `failed` instead.
    isError: results.length > 0 && results.every((r) => r.isError),
    isFetching: results.some((r) => r.isFetching),
    // The shared ErrorState reads `instanceof ApiError` off this to show the
    // status code. Only read when every column failed, so any one will do.
    error: results.find((r) => r.error != null)?.error,
    // Retry every column — a single failed fan-out request is the likeliest
    // failure, so the page's retry must reach it.
    refetch: () => results.forEach((r) => void r.refetch()),
  };
}

/**
 * GAP-118: one bounded request per board column. The board used to bucket the
 * first page of ALL enquiries, so on 5 081 rows every column past the page
 * boundary read as empty or near-empty. Each column now asks for its own
 * status; `useEnquiryStatusCounts` supplies the badges.
 */
export function useEnquiryKanbanColumns(filters: EnquiryFilters, { enabled = true } = {}) {
  return useQueries({
    queries: KANBAN_STATUSES.map((status) => {
      // `page` is the list view's, and each column is its own first page.
      // `ordering` is deliberately passed through, so the board honours the
      // page's sort (and the backend default when there is none).
      const columnFilters: EnquiryFilters = {
        ...filters,
        status,
        page: undefined,
        page_size: KANBAN_COLUMN_PAGE_SIZE,
      };
      return {
        queryKey: queryKeys.enquiries.list(columnFilters),
        queryFn: () => fetchEnquiries(columnFilters),
        enabled,
      };
    }),
    combine: combineKanbanColumns,
  });
}

export function useEnquiryStatusCounts(filters: EnquiryFilters) {
  const query = enquiryStatusCountsQuery(filters);
  return useQuery({
    queryKey: queryKeys.enquiries.statusCounts(query),
    queryFn: () => fetchStatusCounts("/enquiries/status-counts", query),
  });
}

export function useEnquiry(id: EnquiryId | undefined) {
  return useQuery(enabledQuery(id, queryKeys.enquiries.detail, fetchEnquiry));
}

export function useEnquiryActivity(id: EnquiryId | undefined) {
  return useQuery(enabledQuery(id, queryKeys.enquiries.activity, fetchEnquiryActivity));
}

export function useEnquiryNotes(id: EnquiryId | undefined) {
  return useQuery(enabledQuery(id, queryKeys.enquiries.notes, fetchEnquiryNotes));
}

function onDetailUpdated(queryClient: QueryClient, enquiryId: EnquiryId, updated: EnquiryDetail) {
  queryClient.setQueryData(queryKeys.enquiries.detail(enquiryId), updated);
  queryClient.invalidateQueries({ queryKey: queryKeys.enquiries.activity(enquiryId) });
  // Lists, status-count badges, dashboard and the linked person's/agent's
  // contact sub-tabs (BUG-018).
  invalidateEnquiryDependents(queryClient, updated);
}

export function useCreateEnquiry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: EnquiryWriteInput) => createEnquiry(input),
    // The new enquiry appears on lists/badges/dashboard and on the linked
    // person's contact Enquiries tab (BUG-018).
    onSuccess: (created) => invalidateEnquiryDependents(queryClient, created),
  });
}

export function useUpdateEnquiry(enquiryId: EnquiryId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: Partial<EnquiryWriteInput>) => updateEnquiry(enquiryId, input),
    onSuccess: (updated) => onDetailUpdated(queryClient, enquiryId, updated),
  });
}

export function useAssignEnquiry(enquiryId: EnquiryId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: AssignEnquiryInput) => assignEnquiry(enquiryId, input),
    onSuccess: (updated) => onDetailUpdated(queryClient, enquiryId, updated),
  });
}

export function useCloseEnquiry(enquiryId: EnquiryId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CloseEnquiryInput) => closeEnquiry(enquiryId, input),
    onSuccess: (updated) => onDetailUpdated(queryClient, enquiryId, updated),
  });
}

export function useSetLeadStatus(enquiryId: EnquiryId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (value: LeadStatus) => setEnquiryLeadStatus(enquiryId, value),
    onSuccess: (updated) => onDetailUpdated(queryClient, enquiryId, updated),
  });
}

export function useReopenEnquiry(enquiryId: EnquiryId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (reason: string) => reopenEnquiry(enquiryId, reason),
    onSuccess: (updated) => onDetailUpdated(queryClient, enquiryId, updated),
  });
}

export function useConvertEnquiry(enquiryId: EnquiryId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (quotation: number) => convertEnquiry(enquiryId, quotation),
    onSuccess: (updated, quotation) => {
      onDetailUpdated(queryClient, enquiryId, updated);
      // The accepted quotation's status flips server-side too (BUG-018).
      // enquiry/person/agent are null: the enquiry half is covered by
      // onDetailUpdated above, and passing the enquiry id here would
      // re-invalidate the detail key it just setQueryData'd.
      invalidateQuotationDependents(queryClient, {
        id: quotation,
        enquiry: null,
        person: null,
        agent: null,
      });
    },
  });
}

export function useCreateEnquiryNote(enquiryId: EnquiryId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: EnquiryNoteWriteInput) => createEnquiryNote(enquiryId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.enquiries.notes(enquiryId) });
    },
  });
}
