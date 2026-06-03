import { useQuery } from "@tanstack/react-query";
import { ApiError } from "@/lib/api/errors";
import { queryKeys, type BookingId, type PropertyId } from "@/lib/query/keys";
import { enabledQuery } from "@/lib/query/enabledQuery";
import {
  fetchOwnerBooking,
  fetchOwnerBookings,
  fetchOwnerDashboard,
  fetchOwnerMe,
  fetchOwnerProperties,
  fetchOwnerProperty,
  fetchOwnerPropertyCalendar,
} from "./api";
import { useOwnerStore } from "./ownerStore";
import type { OwnerBookingFilters } from "./schemas";

export const OWNER_BOOKINGS_PAGE_SIZE = 50;

// Boot-time owner detection. Probes /owner/me alongside /auth/me. A 403 means
// the authenticated user simply isn't an owner — that's an expected, non-error
// outcome, so we record "not_owner" in the store rather than surfacing a retry.
export function useOwnerMe(enabled: boolean) {
  const setOwner = useOwnerStore((s) => s.setOwner);
  const setNotOwner = useOwnerStore((s) => s.setNotOwner);
  return useQuery({
    queryKey: queryKeys.owner.me(),
    enabled,
    retry: false,
    staleTime: 5 * 60_000,
    queryFn: async () => {
      try {
        const me = await fetchOwnerMe();
        setOwner(me);
        return me;
      } catch (err) {
        if (err instanceof ApiError && (err.status === 403 || err.status === 401)) {
          setNotOwner();
          return null;
        }
        throw err;
      }
    },
  });
}

export function useOwnerDashboard() {
  return useQuery({
    queryKey: queryKeys.owner.dashboard(),
    queryFn: fetchOwnerDashboard,
  });
}

export function useOwnerProperties() {
  return useQuery({
    queryKey: queryKeys.owner.properties({}),
    queryFn: fetchOwnerProperties,
  });
}

export function useOwnerProperty(id: PropertyId | undefined) {
  return useQuery(enabledQuery(id, queryKeys.owner.property, fetchOwnerProperty));
}

export function useOwnerPropertyCalendar(id: PropertyId | undefined, from: string, to: string) {
  return useQuery({
    queryKey: id == null ? ["__disabled__"] : queryKeys.owner.propertyCalendar(id, from, to),
    queryFn: () => fetchOwnerPropertyCalendar(id as PropertyId, from, to),
    enabled: id != null,
  });
}

export function useOwnerBookings(filters: OwnerBookingFilters) {
  return useQuery({
    queryKey: queryKeys.owner.bookings(filters),
    queryFn: () => fetchOwnerBookings(filters),
  });
}

export function useOwnerBooking(id: BookingId | undefined) {
  return useQuery(enabledQuery(id, queryKeys.owner.booking, fetchOwnerBooking));
}
