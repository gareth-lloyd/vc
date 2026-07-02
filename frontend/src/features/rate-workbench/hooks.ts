import { useMutation, useQueries, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { queryKeys, type PropertyId } from "@/lib/query/keys";
import { ApiError } from "@/lib/api/errors";
import { fetchRatePlanDetail, updateRateBand } from "@/features/properties/api";
import type { RatePlanDetail, RateBand } from "@/features/properties/schemas";
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
 * Fan out one `useRatePlanDetail` query per season to assemble the whole rate
 * picture (periods + bands) the timeline needs — `usePropertyRatePlans` returns
 * only the plan envelopes. Keyed on the shared `ratePlanDetail` query key, so
 * any period/band mutation invalidating that key refreshes the timeline and
 * matrix from one cache.
 */
export function useRatePlanDetailsFanOut(seasonIds: number[]) {
  return useQueries({
    queries: seasonIds.map((id) => ({
      queryKey: queryKeys.properties.ratePlanDetail(id),
      queryFn: () => fetchRatePlanDetail(id),
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

export type PriceField = "nightly" | "weekly";

interface PriceEditVars {
  bandId: number;
  field: PriceField;
  value: string;
}
interface PriceEditContext {
  /** The field's cached value before the optimistic patch; undefined = nothing to roll back. */
  previous?: string | null;
}

/** Patch one price field on one band across the plan's periods, clearing POA
 * (a priced cell is not price-on-application). */
function patchBandField(
  detail: RatePlanDetail,
  bandId: number,
  field: PriceField,
  value: string | null,
): RatePlanDetail {
  return {
    ...detail,
    periods: detail.periods.map((period) => ({
      ...period,
      bands: (period.bands ?? []).map((r) =>
        r.id === bandId ? { ...r, [field]: value, is_poa: false } : r,
      ),
    })),
  };
}

/**
 * Optimistic inline price edit (nightly or weekly) for a matrix cell. Mirrors
 * `useToggleBookingNotePin`: patch the shared `ratePlanDetail` cache immediately,
 * PATCH the rule (clearing POA — a priced cell is not price-on-application),
 * roll back + toast on failure, and invalidate on settle so the timeline and
 * matrix reconcile from the server. Structural edits (party bands, POA, clearing
 * a price, new rows/columns) go through `RateBandFormDialog`, not this path.
 *
 * Both fields of one band are fast-editable, so overlapping in-flight edits are
 * possible: rollback restores only the failed field (never a whole-detail
 * snapshot that would revert the other edit), and only the last mutation to
 * settle invalidates (an earlier refetch would predate the later PATCH).
 */
export function useOptimisticBandPrice(ratePlanId: number) {
  const queryClient = useQueryClient();
  const key = queryKeys.properties.ratePlanDetail(ratePlanId);
  const mutationKey = [...key, "inline-price"];
  return useMutation<RateBand, Error, PriceEditVars, PriceEditContext>({
    mutationKey,
    mutationFn: ({ bandId, field, value }) =>
      updateRateBand(
        bandId,
        field === "nightly" ? { nightly: value, is_poa: false } : { weekly: value, is_poa: false },
      ),
    onMutate: async ({ bandId, field, value }) => {
      await queryClient.cancelQueries({ queryKey: key });
      const snapshot = queryClient.getQueryData<RatePlanDetail>(key);
      if (!snapshot) return {};
      const band = snapshot.periods
        .flatMap((period) => period.bands ?? [])
        .find((r) => r.id === bandId);
      queryClient.setQueryData<RatePlanDetail>(key, patchBandField(snapshot, bandId, field, value));
      return band ? { previous: band[field] ?? null } : {};
    },
    onError: (err, { bandId, field }, ctx) => {
      if (ctx && ctx.previous !== undefined) {
        queryClient.setQueryData<RatePlanDetail>(key, (current) =>
          current ? patchBandField(current, bandId, field, ctx.previous ?? null) : current,
        );
      }
      const message =
        err instanceof ApiError
          ? err.detail
          : i18n.t("properties:rate_workbench.matrix.save_failed");
      toast.error(message);
    },
    onSettled: () => {
      if (queryClient.isMutating({ mutationKey }) === 1) {
        void queryClient.invalidateQueries({ queryKey: key });
      }
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
