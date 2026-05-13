import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { queryKeys, type BookingId } from "@/lib/query/keys";
import { enabledQuery } from "@/lib/query/enabledQuery";
import { ApiError } from "@/lib/api/errors";
import type { Paginated } from "@/types/api";
import {
  cancelBooking,
  confirmBooking,
  createBookingNote,
  deleteBookingNote,
  fetchBooking,
  fetchBookingActivity,
  fetchBookingNotes,
  fetchBookings,
  updateBookingNote,
} from "./api";
import type {
  BookingDetail,
  BookingFilters,
  BookingNote,
  BookingNoteWriteInput,
  CancelBookingInput,
} from "./schemas";

export const BOOKINGS_PAGE_SIZE = 50;

export function useBookings(filters: BookingFilters) {
  return useQuery({
    queryKey: queryKeys.bookings.list(filters),
    queryFn: () => fetchBookings(filters),
  });
}

export function useBooking(id: BookingId | undefined) {
  return useQuery(enabledQuery(id, queryKeys.bookings.detail, fetchBooking));
}

export function useBookingActivity(id: BookingId | undefined) {
  return useQuery(enabledQuery(id, queryKeys.bookings.activity, fetchBookingActivity));
}

export function useBookingNotes(id: BookingId | undefined) {
  return useQuery(enabledQuery(id, queryKeys.bookings.notes, fetchBookingNotes));
}

export function useCreateBookingNote(bookingId: BookingId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: BookingNoteWriteInput) => createBookingNote(bookingId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.bookings.notes(bookingId) });
    },
  });
}

interface UpdateNoteVars {
  noteId: number;
  input: Partial<BookingNoteWriteInput>;
}

export function useUpdateBookingNote(bookingId: BookingId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ noteId, input }: UpdateNoteVars) => updateBookingNote(bookingId, noteId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.bookings.notes(bookingId) });
    },
  });
}

export function useDeleteBookingNote(bookingId: BookingId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ noteId }: { noteId: number }) => deleteBookingNote(bookingId, noteId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.bookings.notes(bookingId) });
    },
  });
}

interface ToggleNotePinVars {
  noteId: number;
  is_pinned: boolean;
}

interface ToggleNotePinContext {
  snapshot: Paginated<BookingNote> | undefined;
}

function onActionSuccess(queryClient: QueryClient, bookingId: BookingId, updated: BookingDetail) {
  queryClient.setQueryData(queryKeys.bookings.detail(bookingId), updated);
  queryClient.invalidateQueries({ queryKey: queryKeys.bookings.activity(bookingId) });
  queryClient.invalidateQueries({ queryKey: queryKeys.bookings.lists() });
}

export function useConfirmBooking(bookingId: BookingId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => confirmBooking(bookingId),
    onSuccess: (updated) => onActionSuccess(queryClient, bookingId, updated),
  });
}

export function useCancelBooking(bookingId: BookingId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CancelBookingInput) => cancelBooking(bookingId, input),
    onSuccess: (updated) => onActionSuccess(queryClient, bookingId, updated),
  });
}

export function useToggleBookingNotePin(bookingId: BookingId) {
  const queryClient = useQueryClient();
  const key = queryKeys.bookings.notes(bookingId);
  return useMutation<BookingNote, Error, ToggleNotePinVars, ToggleNotePinContext>({
    mutationFn: ({ noteId, is_pinned }) => updateBookingNote(bookingId, noteId, { is_pinned }),
    onMutate: async ({ noteId, is_pinned }) => {
      await queryClient.cancelQueries({ queryKey: key });
      const snapshot = queryClient.getQueryData<Paginated<BookingNote>>(key);
      if (snapshot) {
        queryClient.setQueryData<Paginated<BookingNote>>(key, {
          ...snapshot,
          results: snapshot.results.map((n) => (n.id === noteId ? { ...n, is_pinned } : n)),
        });
      }
      return { snapshot };
    },
    onError: (err, _vars, ctx) => {
      if (ctx?.snapshot) queryClient.setQueryData(key, ctx.snapshot);
      const message = err instanceof ApiError ? err.detail : "Couldn't update pin";
      toast.error(message);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: key });
    },
  });
}
