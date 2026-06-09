import { describe, expect, it } from "vitest";
import { lastNight, nightRangeParts, nightsCount } from "./nights";

describe("lastNight", () => {
  it("returns the night before the exclusive checkout date", () => {
    // [21 Jul, 31 Jul) → last night slept is the 30th
    expect(lastNight("2026-07-31")).toEqual(new Date(2026, 6, 30));
  });

  it("handles a single-night range (checkout the morning after)", () => {
    // [21 Jul, 22 Jul) → last night is the 21st
    expect(lastNight("2026-07-22")).toEqual(new Date(2026, 6, 21));
  });

  it("steps back across a month boundary", () => {
    // [29 Jul, 1 Aug) → last night is 31 Jul
    expect(lastNight("2026-08-01")).toEqual(new Date(2026, 6, 31));
  });
});

describe("nightsCount", () => {
  it("counts nights in a half-open range", () => {
    expect(nightsCount("2026-07-21", "2026-07-31")).toBe(10);
  });

  it("counts a single night", () => {
    expect(nightsCount("2026-07-21", "2026-07-22")).toBe(1);
  });

  it("spans a month boundary", () => {
    expect(nightsCount("2026-07-29", "2026-08-01")).toBe(3);
  });

  it("returns zero for a degenerate range", () => {
    expect(nightsCount("2026-07-21", "2026-07-21")).toBe(0);
  });
});

describe("nightRangeParts", () => {
  it("returns first night, last night and a nights count for a multi-night range", () => {
    expect(nightRangeParts("2026-07-21", "2026-07-31")).toEqual({
      firstNight: new Date(2026, 6, 21),
      lastNight: new Date(2026, 6, 30),
      nights: 10,
    });
  });

  it("collapses a single-night range so first and last night coincide", () => {
    expect(nightRangeParts("2026-07-21", "2026-07-22")).toEqual({
      firstNight: new Date(2026, 6, 21),
      lastNight: new Date(2026, 6, 21),
      nights: 1,
    });
  });

  it("spans a year boundary", () => {
    expect(nightRangeParts("2026-12-30", "2027-01-02")).toEqual({
      firstNight: new Date(2026, 11, 30),
      lastNight: new Date(2027, 0, 1),
      nights: 3,
    });
  });
});
