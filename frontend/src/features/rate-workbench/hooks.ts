import { useMutation, useQueries, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { queryKeys, type PropertyId } from "@/lib/query/keys";
import { ApiError } from "@/lib/api/errors";
import { fetchSeasonDetail, updateRateRule } from "@/features/properties/api";
import type { RatePlanDetail, RateRule } from "@/features/properties/schemas";
import i18n from "@/i18n";
import {
  createDiscount,
  createExtra,
  deleteDiscount,
  deleteExtra,
  runPriceProbe,
  updateDiscount,
  updateExtra,
} from "./api";
import type { DiscountWritePayload, ExtraWritePayload } from "./schemas";

/**
 * Fan out one `useSeasonDetail` query per season to assemble the whole rate
 * picture (periods + bands) the timeline needs — `usePropertySeasons` returns
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
          periods: snapshot.periods.map((period) => ({
            ...period,
            rules: (period.rules ?? []).map((r) =>
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

// ---------------------------------------------------------------------------
// Inspector CRUD (Unit 5): Extras + Discounts. Inclusions reuse the existing
// PropertyService hooks in `@/features/properties/hooks`. Each mutation
// invalidates the same list query key the page's read hooks already observe,
// so the inspector and the timeline reconcile from one cache.
// ---------------------------------------------------------------------------

export function useCreateExtra(propertyId: PropertyId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: ExtraWritePayload) => createExtra(propertyId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.extras(propertyId) });
    },
  });
}

interface UpdateExtraVars {
  extraId: number;
  input: Partial<ExtraWritePayload>;
}

export function useUpdateExtra(propertyId: PropertyId) {
  const queryClient = useQueryClient();
  return useMutation({
    // Detail route is flat, so the extra id alone addresses the row; propertyId
    // is carried only to invalidate the right list cache.
    mutationFn: ({ extraId, input }: UpdateExtraVars) => updateExtra(extraId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.extras(propertyId) });
    },
  });
}

export function useDeleteExtra(propertyId: PropertyId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ extraId }: { extraId: number }) => deleteExtra(extraId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.extras(propertyId) });
    },
  });
}

export function useCreateDiscount(propertyId: PropertyId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: DiscountWritePayload) => createDiscount(propertyId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.discounts(propertyId) });
    },
  });
}

interface UpdateDiscountVars {
  discountId: number;
  input: Partial<DiscountWritePayload>;
}

export function useUpdateDiscount(propertyId: PropertyId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ discountId, input }: UpdateDiscountVars) => updateDiscount(discountId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.discounts(propertyId) });
    },
  });
}

export function useDeleteDiscount(propertyId: PropertyId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ discountId }: { discountId: number }) => deleteDiscount(discountId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.discounts(propertyId) });
    },
  });
}

/**
 * Live guest-side price probe (Unit 6). Read-only — an explicit "Get quote"
 * mutation, no cache writes/invalidation. Domain failures (e.g.
 * `no_rate_available`) reject with a 409 `ApiError` the panel renders inline.
 */
export function usePriceProbe() {
  return useMutation({ mutationFn: runPriceProbe });
}
