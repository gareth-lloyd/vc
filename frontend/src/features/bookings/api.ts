import { apiGet, apiSend } from "@/lib/api/client";
import type { QueryParams } from "@/lib/api/url";
import type { Paginated } from "@/types/api";
import type { BookingId } from "@/lib/query/keys";
import {
  bookingActivityResponseSchema,
  bookingConciergeItemsResponseSchema,
  bookingDetailSchema,
  bookingListResponseSchema,
  bookingNoteSchema,
  bookingNotesResponseSchema,
  type BookingConciergeItem,
  type BookingDetail,
  type BookingEvent,
  type BookingFilters,
  type BookingListItem,
  type BookingNote,
  type BookingNoteWriteInput,
  type CancelBookingInput,
} from "./schemas";

function toQuery(filters: BookingFilters): QueryParams {
  return {
    q: filters.q || undefined,
    status: filters.status || undefined,
    site: filters.site || undefined,
    ordering: filters.ordering || undefined,
    page: filters.page && filters.page > 1 ? filters.page : undefined,
  };
}

export async function fetchBookings(filters: BookingFilters): Promise<Paginated<BookingListItem>> {
  const data = await apiGet<unknown>("/bookings", { query: toQuery(filters) });
  return bookingListResponseSchema.parse(data);
}

export async function fetchBooking(id: BookingId): Promise<BookingDetail> {
  const data = await apiGet<unknown>(`/bookings/${id}`);
  return bookingDetailSchema.parse(data);
}

export async function fetchBookingActivity(id: BookingId): Promise<Paginated<BookingEvent>> {
  const data = await apiGet<unknown>(`/bookings/${id}/activity`);
  return bookingActivityResponseSchema.parse(data);
}

export async function fetchBookingNotes(id: BookingId): Promise<Paginated<BookingNote>> {
  const data = await apiGet<unknown>(`/bookings/${id}/notes`);
  return bookingNotesResponseSchema.parse(data);
}

export async function fetchBookingConciergeItems(
  id: BookingId,
): Promise<Paginated<BookingConciergeItem>> {
  const data = await apiGet<unknown>(`/bookings/${id}/concierge-items`);
  return bookingConciergeItemsResponseSchema.parse(data);
}

export async function createBookingNote(
  bookingId: BookingId,
  body: BookingNoteWriteInput,
): Promise<BookingNote> {
  const data = await apiSend<unknown>("POST", `/bookings/${bookingId}/notes`, body);
  return bookingNoteSchema.parse(data);
}

export async function updateBookingNote(
  bookingId: BookingId,
  noteId: number,
  body: Partial<BookingNoteWriteInput>,
): Promise<BookingNote> {
  const data = await apiSend<unknown>("PATCH", `/bookings/${bookingId}/notes/${noteId}`, body);
  return bookingNoteSchema.parse(data);
}

export async function deleteBookingNote(bookingId: BookingId, noteId: number): Promise<void> {
  await apiSend<void>("DELETE", `/bookings/${bookingId}/notes/${noteId}`);
}

export async function confirmBooking(id: BookingId): Promise<BookingDetail> {
  const data = await apiSend<unknown>("POST", `/bookings/${id}:confirm`);
  return bookingDetailSchema.parse(data);
}

export async function cancelBooking(
  id: BookingId,
  body: CancelBookingInput,
): Promise<BookingDetail> {
  const data = await apiSend<unknown>("POST", `/bookings/${id}:cancel`, body);
  return bookingDetailSchema.parse(data);
}
