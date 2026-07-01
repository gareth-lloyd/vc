import type { LaneKey } from "../toLanes";

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
  inclusions: "bg-success/20 border-success/50",
  extras: "bg-warning/25 border-warning/60",
  discounts: "bg-accent border-accent-foreground/30",
  changeover: "bg-muted border-muted-foreground/40",
};
