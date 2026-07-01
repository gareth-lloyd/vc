import { useQueries } from "@tanstack/react-query";
import { queryKeys } from "@/lib/query/keys";
import { fetchSeasonDetail } from "@/features/properties/api";
import type { RatePlanDetail } from "@/features/properties/schemas";

/**
 * Fan out one `useSeasonDetail` query per season to assemble the whole rate
 * picture (cards + rules) the timeline needs — `usePropertySeasons` returns
 * only the plan envelopes. Keyed on the shared `seasonDetail` query key so the
 * cache is deduped with `PricingTab`'s `SeasonDetailPanel`, and any RateRule
 * mutation invalidating that key refreshes the workbench too.
 */
export function useSeasonDetailsFanOut(seasonIds: number[]) {
  return useQueries({
    queries: seasonIds.map((id) => ({
      queryKey: queryKeys.properties.seasonDetail(id),
      queryFn: () => fetchSeasonDetail(id),
    })),
    combine: (results) => ({
      details: results.map((r) => r.data).filter((d): d is RatePlanDetail => d != null),
      isLoading: results.some((r) => r.isLoading),
      isError: results.some((r) => r.isError),
      // Retry every fan-out query — a failed season-detail is the likeliest
      // per-request failure, so the page's error-retry must reach it too.
      refetch: () => results.forEach((r) => void r.refetch()),
    }),
  });
}
