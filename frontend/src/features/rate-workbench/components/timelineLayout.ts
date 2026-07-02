import type { LaneKey, WorkbenchBand } from "../toLanes";

/** Pixel geometry for the stacked-lane timeline. */
export const BAND_HEIGHT = 18;
export const SUBLANE_GAP = 4;
export const LANE_V_PADDING = 8;

/** Height of a lane track given its deepest sub-lane index. */
export function laneHeight(maxSublane: number): number {
  const rows = maxSublane + 1;
  return rows * BAND_HEIGHT + (rows - 1) * SUBLANE_GAP + LANE_V_PADDING * 2;
}

/** Top offset (px) of a band at the given sub-lane. */
export function bandTop(sublane: number): number {
  return LANE_V_PADDING + sublane * (BAND_HEIGHT + SUBLANE_GAP);
}

/** Tone → token-driven fill + border classes (no raw Tailwind colours). */
export const TONE_CLASS: Record<LaneKey, string> = {
  seasons: "bg-primary/20 border-primary/50",
  rates: "bg-info/20 border-info/50",
  coverage: "bg-warning/10 border-warning/60 border-dashed",
  inclusions: "bg-success/20 border-success/50",
  extras: "bg-warning/25 border-warning/60",
  discounts: "bg-accent border-accent-foreground/30",
  changeover: "bg-muted border-muted-foreground/40",
};

/** Rate bands: cheap→expensive read as low→high info intensity. */
const RATE_TIER_CLASS: Record<NonNullable<WorkbenchBand["meta"]["priceTier"]>, string> = {
  low: "bg-info/10 border-info/40",
  mid: "bg-info/25 border-info/60",
  high: "bg-info/45 border-info/80",
};

/** Extras: mandatory reads stronger than optional. */
const EXTRA_MANDATORY_CLASS = "bg-warning/45 border-warning/70";
const EXTRA_OPTIONAL_CLASS = "bg-warning/15 border-warning/40";

/** Rates: a period with no bands yet — an outline, not a priced fill. */
const RATE_NO_RATES_CLASS = "bg-transparent border-info/40 border-dashed";

/**
 * The fill+border classes for a band, coloured by *meaning* rather than lane
 * alone: rate bands by price tier (zero-band periods as a dashed outline),
 * extras by mandatory-vs-optional, everything else by the flat lane tone.
 * Untiered rate bands (all-POA) fall back to the lane tone.
 */
export function bandToneClass(band: WorkbenchBand): string {
  if (band.laneKey === "rates" && band.meta.noRates) {
    return RATE_NO_RATES_CLASS;
  }
  if (band.laneKey === "rates" && band.meta.priceTier) {
    return RATE_TIER_CLASS[band.meta.priceTier];
  }
  if (band.laneKey === "extras") {
    return band.meta.isMandatory ? EXTRA_MANDATORY_CLASS : EXTRA_OPTIONAL_CLASS;
  }
  return TONE_CLASS[band.laneKey];
}
