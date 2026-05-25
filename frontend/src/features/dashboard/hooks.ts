import { useQuery } from "@tanstack/react-query";
import { queryKeys } from "@/lib/query/keys";
import {
  fetchArrivalsToday,
  fetchAwaitingBalanceCount,
  fetchDeparturesTodayCount,
  fetchNewEnquiriesCount,
  fetchRecentEnquiries,
} from "./api";

export function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export function useArrivalsToday() {
  const today = todayIso();
  return useQuery({
    queryKey: queryKeys.dashboard.arrivalsToday(today),
    queryFn: () => fetchArrivalsToday(today),
  });
}

export function useDeparturesTodayCount() {
  const today = todayIso();
  return useQuery({
    queryKey: queryKeys.dashboard.departuresTodayCount(today),
    queryFn: () => fetchDeparturesTodayCount(today),
  });
}

export function useNewEnquiriesCount() {
  return useQuery({
    queryKey: queryKeys.dashboard.newEnquiriesCount(),
    queryFn: fetchNewEnquiriesCount,
  });
}

export function useAwaitingBalanceCount() {
  return useQuery({
    queryKey: queryKeys.dashboard.awaitingBalanceCount(),
    queryFn: fetchAwaitingBalanceCount,
  });
}

export function useRecentEnquiries() {
  return useQuery({
    queryKey: queryKeys.dashboard.recentEnquiries(),
    queryFn: fetchRecentEnquiries,
  });
}
