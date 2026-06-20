import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys, type BookingId, type PropertyId } from "@/lib/query/keys";
import { enabledQuery } from "@/lib/query/enabledQuery";
import {
  approveOwnerBooking,
  cancelOwnerBlockRequest,
  createOwnerBlockRequest,
  declineOwnerBooking,
  fetchOwnerBlockRequests,
  fetchOwnerBooking,
  fetchOwnerBookings,
  fetchOwnerDashboard,
  fetchOwnerMe,
  fetchOwnerProperties,
  fetchOwnerProperty,
  fetchOwnerPropertyCalendar,
} from "./api";
import { useOwnerStore } from "./ownerStore";
import type {
  BlockRequestWriteInput,
  OwnerBlockRequestFilters,
  OwnerBookingFilters,
} from "./schemas";

// Block requests live under a property's availability; invalidating the
// property prefix sweeps its calendar (and detail) without enumerating ranges.
const OWNER_BLOCK_REQUESTS_KEY = ["owner", "block-requests"] as const;
const OWNER_BOOKINGS_KEY = ["owner", "bookings"] as const;

export const OWNER_BOOKINGS_PAGE_SIZE = 50;

// Boot-time owner detection. Probes /owner/me alongside /auth/me. The endpoint
// returns 200 for any authenticated user: is_owner:true with organisations for
// an owner, or is_owner:false with an empty list for a non-owner. We branch on
// that body — no 403-as-control-flow, so a staff boot logs no console error.
export function useOwnerMe(enabled: boolean) {
  const setOwner = useOwnerStore((s) => s.setOwner);
  const setNotOwner = useOwnerStore((s) => s.setNotOwner);
  const setProbeError = useOwnerStore((s) => s.setProbeError);
  return useQuery({
    queryKey: queryKeys.owner.me(),
    enabled,
    retry: false,
    staleTime: 5 * 60_000,
    queryFn: async () => {
      try {
        const me = await fetchOwnerMe();
        if (me.is_owner) setOwner(me);
        else setNotOwner();
        return me;
      } catch (err) {
        // Not-owner is now a 200 body, so any thrown error (5xx/network/parse)
        // is indeterminate. Record a retryable error state rather than a false
        // "not_owner": with retry:false + staleTime 5min, a "not_owner" verdict
        // would lock a genuine owner out of their portal for five minutes on a
        // single transient blip. The guards surface a retry.
        setProbeError();
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

export function useOwnerBlockRequests(filters: OwnerBlockRequestFilters = {}) {
  return useQuery({
    queryKey: queryKeys.owner.blockRequests(filters),
    queryFn: () => fetchOwnerBlockRequests(filters),
  });
}

export function useCreateBlockRequest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: BlockRequestWriteInput) => createOwnerBlockRequest(input),
    onSuccess: (request) => {
      void queryClient.invalidateQueries({ queryKey: OWNER_BLOCK_REQUESTS_KEY });
      void queryClient.invalidateQueries({ queryKey: queryKeys.owner.property(request.property) });
    },
  });
}

export function useCancelBlockRequest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => cancelOwnerBlockRequest(id),
    onSuccess: (request) => {
      void queryClient.invalidateQueries({ queryKey: OWNER_BLOCK_REQUESTS_KEY });
      void queryClient.invalidateQueries({ queryKey: queryKeys.owner.property(request.property) });
    },
  });
}

function invalidateAfterBookingDecision(
  queryClient: ReturnType<typeof useQueryClient>,
  id: BookingId,
): void {
  void queryClient.invalidateQueries({ queryKey: queryKeys.owner.booking(id) });
  void queryClient.invalidateQueries({ queryKey: OWNER_BOOKINGS_KEY });
  void queryClient.invalidateQueries({ queryKey: queryKeys.owner.dashboard() });
}

export function useApproveBooking(id: BookingId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => approveOwnerBooking(id),
    onSuccess: () => invalidateAfterBookingDecision(queryClient, id),
  });
}

export function useDeclineBooking(id: BookingId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (reason: string) => declineOwnerBooking(id, reason),
    onSuccess: () => invalidateAfterBookingDecision(queryClient, id),
  });
}
