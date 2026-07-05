import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
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
import type {
  AssignEnquiryInput,
  CloseEnquiryInput,
  EnquiryDetail,
  EnquiryFilters,
  EnquiryNoteWriteInput,
  EnquiryWriteInput,
} from "./schemas";
import type { LeadStatus } from "@/styles/tokens";

export const ENQUIRIES_PAGE_SIZE = 50;

export function useEnquiries(filters: EnquiryFilters) {
  return useQuery({
    queryKey: queryKeys.enquiries.list(filters),
    queryFn: () => fetchEnquiries(filters),
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
      // enquiry/guest/agent are null: the enquiry half is covered by
      // onDetailUpdated above, and passing the enquiry id here would
      // re-invalidate the detail key it just setQueryData'd.
      invalidateQuotationDependents(queryClient, {
        id: quotation,
        enquiry: null,
        guest: null,
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
