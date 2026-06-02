import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { queryKeys, type EnquiryId } from "@/lib/query/keys";
import { enabledQuery } from "@/lib/query/enabledQuery";
import {
  assignEnquiry,
  closeEnquiry,
  convertEnquiry,
  createEnquiry,
  createEnquiryNote,
  fetchEnquiries,
  fetchEnquiryStatusCounts,
  fetchEnquiry,
  fetchEnquiryActivity,
  fetchEnquiryNotes,
  patchEnquiryStatus,
  reopenEnquiry,
  updateEnquiry,
} from "./api";
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

export const ENQUIRIES_PAGE_SIZE = 50;

export function useEnquiries(filters: EnquiryFilters) {
  return useQuery({
    queryKey: queryKeys.enquiries.list(filters),
    queryFn: () => fetchEnquiries(filters),
  });
}

export function useEnquiryStatusCounts(filters: EnquiryFilters) {
  return useQuery({
    queryKey: queryKeys.enquiries.statusCounts(filters),
    queryFn: () => fetchEnquiryStatusCounts(filters),
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
  queryClient.invalidateQueries({ queryKey: queryKeys.enquiries.lists() });
  queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.all() });
}

export function useCreateEnquiry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: EnquiryWriteInput) => createEnquiry(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.enquiries.lists() });
      queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.all() });
    },
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
    onSuccess: (updated) => onDetailUpdated(queryClient, enquiryId, updated),
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

// Kanban drag-drop: drop card on a column → call the matching verb endpoint.
// Routes through patchEnquiryStatus which knows which verb to call.
interface MoveEnquiryVars {
  enquiry: EnquiryListItem;
  toStatus: EnquiryStatus;
}

export function useMoveEnquiry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ enquiry, toStatus }: MoveEnquiryVars) =>
      patchEnquiryStatus(enquiry.id, toStatus),
    onSuccess: (updated) => {
      onDetailUpdated(queryClient, updated.id, updated);
    },
  });
}
