import { useMutation, useQueries, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { queryKeys } from "@/lib/query/keys";
import { ApiError } from "@/lib/api/errors";
import { fetchSeasonDetail, updateRateRule } from "@/features/properties/api";
import type { RatePlanDetail, RateRule } from "@/features/properties/schemas";
import i18n from "@/i18n";

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

interface NightlyEditVars {
  ruleId: number;
  nightly: string;
}
interface NightlyEditContext {
  snapshot?: RatePlanDetail;
}

/**
 * Optimistic inline nightly-price edit for a matrix cell. Mirrors
 * `useToggleBookingNotePin`: patch the shared `seasonDetail` cache immediately,
 * PATCH the rule (clearing POA — a priced cell is not price-on-application),
 * roll back + toast on failure, and invalidate on settle so the timeline and
 * matrix reconcile from the server. Structural edits (party bands, weekly, POA,
 * new rows/columns) go through `RateRuleFormDialog`, not this path.
 */
export function useOptimisticRuleNightly(seasonId: number) {
  const queryClient = useQueryClient();
  const key = queryKeys.properties.seasonDetail(seasonId);
  return useMutation<RateRule, Error, NightlyEditVars, NightlyEditContext>({
    mutationFn: ({ ruleId, nightly }) => updateRateRule(ruleId, { nightly, is_poa: false }),
    onMutate: async ({ ruleId, nightly }) => {
      await queryClient.cancelQueries({ queryKey: key });
      const snapshot = queryClient.getQueryData<RatePlanDetail>(key);
      if (snapshot) {
        queryClient.setQueryData<RatePlanDetail>(key, {
          ...snapshot,
          cards: snapshot.cards.map((c) => ({
            ...c,
            rules: (c.rules ?? []).map((r) =>
              r.id === ruleId ? { ...r, nightly, is_poa: false } : r,
            ),
          })),
        });
      }
      return { snapshot };
    },
    onError: (err, _vars, ctx) => {
      if (ctx?.snapshot) queryClient.setQueryData(key, ctx.snapshot);
      const message =
        err instanceof ApiError
          ? err.detail
          : i18n.t("properties:rate_workbench.matrix.save_failed");
      toast.error(message);
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: key });
    },
  });
}
