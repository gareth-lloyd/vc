import { useQuery } from "@tanstack/react-query";
import { queryKeys, type BookingId } from "@/lib/query/keys";
import { enabledQuery } from "@/lib/query/enabledQuery";
import { fetchBooking, fetchBookingActivity, fetchBookings } from "./api";
import type { BookingFilters } from "./schemas";

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
