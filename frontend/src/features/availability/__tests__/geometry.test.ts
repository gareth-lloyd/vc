import { describe, expect, it } from "vitest";
import { parseISO } from "date-fns";
import { assignLanes, bandGeometry } from "../geometry";

const WINDOW_START = parseISO("2026-06-01"); // a Monday
const DAYS = 35;

const pct = (days: number) => (days / DAYS) * 100;

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
      assignLanes([
        { date_from: "2026-06-01", date_to: "2026-06-08" },
        { date_from: "2026-06-10", date_to: "2026-06-14" },
      ]),
    ).toEqual([0, 0]);
  });

  it("keeps same-day turnover in one lane (exclusive checkout)", () => {
    expect(
      assignLanes([
        { date_from: "2026-06-01", date_to: "2026-06-08" },
        { date_from: "2026-06-08", date_to: "2026-06-14" },
      ]),
    ).toEqual([0, 0]);
  });

  it("stacks genuinely overlapping bands into separate lanes", () => {
    expect(
      assignLanes([
        { date_from: "2026-06-01", date_to: "2026-06-10" },
        { date_from: "2026-06-05", date_to: "2026-06-12" },
      ]),
    ).toEqual([0, 1]);
  });

  it("reuses a freed lane and preserves input order", () => {
    const lanes = assignLanes([
      { date_from: "2026-06-05", date_to: "2026-06-12" }, // overlaps first two
      { date_from: "2026-06-01", date_to: "2026-06-08" },
      { date_from: "2026-06-12", date_to: "2026-06-15" }, // fits after the first
    ]);
    expect(lanes).toHaveLength(3);
    expect(lanes[0]).not.toBe(lanes[1]);
    // Third band starts when the first ends — slots back into a low lane.
    expect(Math.max(...lanes)).toBe(1);
  });
});
