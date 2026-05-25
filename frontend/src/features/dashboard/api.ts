import { apiGet } from "@/lib/api/client";
import type { Paginated } from "@/types/api";
import { bookingListResponseSchema, type BookingListItem } from "@/features/bookings/schemas";
import { enquiryListResponseSchema, type EnquiryListItem } from "@/features/enquiries/schemas";

export async function fetchArrivalsToday(today: string): Promise<Paginated<BookingListItem>> {
  const data = await apiGet<unknown>("/bookings", {
    query: { check_in_after: today, check_in_before: today, ordering: "date_from" },
  });
  return bookingListResponseSchema.parse(data);
}

export async function fetchDeparturesTodayCount(today: string): Promise<number> {
  const data = await apiGet<unknown>("/bookings", {
    query: { check_out_after: today, check_out_before: today },
  });
  return bookingListResponseSchema.parse(data).count;
}

export async function fetchNewEnquiriesCount(): Promise<number> {
  const data = await apiGet<unknown>("/enquiries", {
    query: { status: "new" },
  });
  return enquiryListResponseSchema.parse(data).count;
}

export async function fetchAwaitingBalanceCount(): Promise<number> {
  const data = await apiGet<unknown>("/bookings", {
    query: { status: "awaiting_balance" },
  });
  return bookingListResponseSchema.parse(data).count;
}

export async function fetchRecentEnquiries(): Promise<Paginated<EnquiryListItem>> {
  const data = await apiGet<unknown>("/enquiries", {
    query: { ordering: "-created_at" },
  });
  return enquiryListResponseSchema.parse(data);
}
