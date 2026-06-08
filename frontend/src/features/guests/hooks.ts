import { useQuery } from "@tanstack/react-query";
import { queryKeys, type GuestId } from "@/lib/query/keys";
import { enabledQuery } from "@/lib/query/enabledQuery";
import { fetchGuest, fetchGuestEnquiries, searchGuests } from "./api";

export function useSearchGuests(query: string) {
  return useQuery({
    queryKey: queryKeys.guests.search(query),
    queryFn: () => searchGuests(query),
    enabled: query.length >= 2,
  });
}

export function useGuest(id: GuestId | undefined) {
  return useQuery(enabledQuery(id, queryKeys.guests.detail, fetchGuest));
}

export function useGuestEnquiries(id: GuestId | undefined) {
  return useQuery(enabledQuery(id, queryKeys.guests.enquiries, fetchGuestEnquiries));
}
