import { apiGet } from "@/lib/api/client";
import type { GuestId } from "@/lib/query/keys";
import type { Paginated } from "@/types/api";
import {
  guestEnquiryHistoryResponseSchema,
  guestSchema,
  guestsSearchResponseSchema,
  type Guest,
  type GuestEnquiryHistoryItem,
} from "./schemas";

/**
 * Resolve existing guests for the enquiry picker. Filters to `status=active`:
 * ANONYMIZED (GDPR-redacted, `email=null`) and ARCHIVED guests must never be
 * linkable to a new enquiry — doing so would prefill blanks or re-link a
 * redacted row. The `/guests` search itself has no status floor, so the
 * constraint lives here, on the consumer.
 */
export async function searchGuests(query: string): Promise<Paginated<Guest>> {
  const data = await apiGet<unknown>("/guests", {
    query: { search: query, status: "active" },
  });
  return guestsSearchResponseSchema.parse(data);
}

export async function fetchGuest(id: GuestId): Promise<Guest> {
  const data = await apiGet<unknown>(`/guests/${id}`);
  return guestSchema.parse(data);
}

export async function fetchGuestEnquiries(
  guestId: GuestId,
): Promise<Paginated<GuestEnquiryHistoryItem>> {
  const data = await apiGet<unknown>(`/guests/${guestId}/enquiries`);
  return guestEnquiryHistoryResponseSchema.parse(data);
}
