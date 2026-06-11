import { describe, expect, it } from "vitest";
import { parseISO } from "date-fns";
import { assignLanes, bandEdges, bandGeometry } from "../geometry";

const WINDOW_START = parseISO("2026-06-01"); // a Monday
const DAYS = 35;

const pct = (days: number) => (days / DAYS) * 100;

/** Rendered edges for a hold (whole-cell) or booking (half-cell shifted). */
const hold = (from: string, to: string) => bandEdges(from, to, WINDOW_START);
const booking = (from: string, to: string) =>
  bandEdges(from, to, WINDOW_START, { halfDayOffset: true });

describe("bandGeometry", () => {
  it("places a hold band on whole-cell boundaries", () => {
    const geo = bandGeometry("2026-06-03", "2026-06-08", WINDOW_START, DAYS);
    expect(geo).toEqual({ leftPct: pct(2), widthPct: pct(5) });
  });

  it("offsets a booking band by half a cell (mid check-in cell → mid checkout cell)", () => {
    const geo = bandGeometry("2026-06-03", "2026-06-08", WINDOW_START, DAYS, {
      halfDayOffset: true,
    });
    expect(geo).toEqual({ leftPct: pct(2.5), widthPct: pct(5) });
  });

  it("renders same-day turnover as kissing bands, no overlap", () => {
    const a = bandGeometry("2026-06-01", "2026-06-08", WINDOW_START, DAYS, {
      halfDayOffset: true,
    });
    const b = bandGeometry("2026-06-08", "2026-06-14", WINDOW_START, DAYS, {
      halfDayOffset: true,
    });
    expect(a).not.toBeNull();
    expect(b).not.toBeNull();
    expect(a!.leftPct + a!.widthPct).toBeCloseTo(b!.leftPct);
  });

  it("clamps a band overhanging the window start", () => {
    const geo = bandGeometry("2026-05-20", "2026-06-05", WINDOW_START, DAYS);
    expect(geo).toEqual({ leftPct: 0, widthPct: pct(4) });
  });

  it("clamps a band overhanging the window end", () => {
    const geo = bandGeometry("2026-07-03", "2026-07-20", WINDOW_START, DAYS);
    expect(geo).toEqual({ leftPct: pct(32), widthPct: pct(3) });
  });

  it("returns null for bands entirely outside the window", () => {
    expect(bandGeometry("2026-05-01", "2026-05-20", WINDOW_START, DAYS)).toBeNull();
    expect(bandGeometry("2026-08-01", "2026-08-08", WINDOW_START, DAYS)).toBeNull();
    // Exclusive checkout on the window start day: nothing to paint.
    expect(bandGeometry("2026-05-25", "2026-06-01", WINDOW_START, DAYS)).toBeNull();
  });

  it("paints a one-night stay one cell wide", () => {
    const geo = bandGeometry("2026-06-03", "2026-06-04", WINDOW_START, DAYS);
    expect(geo).toEqual({ leftPct: pct(2), widthPct: pct(1) });
  });
});

describe("assignLanes", () => {
  it("keeps non-overlapping bands in lane 0", () => {
    expect(
      assignLanes([hold("2026-06-01", "2026-06-08"), hold("2026-06-10", "2026-06-14")]),
    ).toEqual([0, 0]);
  });

  it("keeps same-day booking turnover in one lane (exclusive checkout)", () => {
    expect(
      assignLanes([booking("2026-06-01", "2026-06-08"), booking("2026-06-08", "2026-06-14")]),
    ).toEqual([0, 0]);
  });

  it("stacks genuinely overlapping bands into separate lanes", () => {
    expect(
      assignLanes([hold("2026-06-01", "2026-06-10"), hold("2026-06-05", "2026-06-12")]),
    ).toEqual([0, 1]);
  });

  it("stacks a hold starting on a booking's checkout day (the rendered bands overlap)", () => {
    // The booking paints until mid-cell on 8 Jun; a hold covering 8 Jun from
    // midnight overlaps that half-cell and must not share the lane.
    expect(
      assignLanes([booking("2026-06-01", "2026-06-08"), hold("2026-06-08", "2026-06-14")]),
    ).toEqual([0, 1]);
  });

  it("keeps a hold ending on a booking's check-in day in one lane", () => {
    // The hold ends at the cell edge; the booking starts mid-cell — no overlap.
    expect(
      assignLanes([hold("2026-06-01", "2026-06-08"), booking("2026-06-08", "2026-06-14")]),
    ).toEqual([0, 0]);
  });

  it("reuses a freed lane and preserves input order", () => {
    const lanes = assignLanes([
      hold("2026-06-05", "2026-06-12"), // overlaps first two
      hold("2026-06-01", "2026-06-08"),
      hold("2026-06-12", "2026-06-15"), // fits after the first
    ]);
    expect(lanes).toHaveLength(3);
    expect(lanes[0]).not.toBe(lanes[1]);
    // Third band starts when the first ends — slots back into a low lane.
    expect(Math.max(...lanes)).toBe(1);
  });
});
