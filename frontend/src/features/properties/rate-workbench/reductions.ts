import type { RateBand } from "@/features/properties/schemas";

/**
 * Q-018 reduction derivations shared by the matrix cells and the timeline
 * lanes. A band's reduction is percent XOR fixed reduced prices; the server's
 * `effective_*` fields are authoritative, but they go stale mid-optimistic-edit
 * (the cache patches only the edited BASE field) and are absent on pre-Q-018
 * shapes — so display sites derive the reduced figure from the reduction
 * fields themselves, keeping the hint coherent with the base on screen.
 */

type ReductionFields = Pick<
  RateBand,
  "nightly" | "weekly" | "reduction_percent" | "reduced_nightly" | "reduced_weekly"
>;

/** True when the band carries a reduction (percent XOR fixed reduced prices). */
export function bandHasReduction(band: ReductionFields): boolean {
  return !!band.reduction_percent || !!band.reduced_nightly || !!band.reduced_weekly;
}

/**
 * The reduced price for one axis, derived from the band's own reduction
 * fields: fixed → that axis's `reduced_*`; percent → base×(100−p)/100 rounded
 * to 2dp (display rounding only — a refetch normalises any half-even penny).
 * Null when the axis carries no reduction or has no base price, so callers can
 * use it both as the figure and as the per-axis "is reduced" gate.
 */
export function derivedReducedPrice(
  band: ReductionFields,
  axis: "nightly" | "weekly",
): string | null {
  const base = axis === "nightly" ? band.nightly : band.weekly;
  if (!base) return null;
  const fixed = axis === "nightly" ? band.reduced_nightly : band.reduced_weekly;
  if (fixed) return fixed;
  if (!band.reduction_percent) return null;
  const baseNum = Number(base);
  const percent = Number(band.reduction_percent);
  if (!Number.isFinite(baseNum) || !Number.isFinite(percent)) return null;
  return ((baseNum * (100 - percent)) / 100).toFixed(2);
}
