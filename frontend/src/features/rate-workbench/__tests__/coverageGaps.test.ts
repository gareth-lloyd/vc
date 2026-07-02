import { describe, expect, it } from "vitest";
import { coverageDateGaps } from "../coverageGaps";

// The 2026 window: inclusive Jan 1 → exclusive Jan 1 2027 (yearWindow shape).
const win = { windowFrom: "2026-01-01", windowTo: "2027-01-01" };

const period = (date_from: string, date_to: string, is_active = true) => ({
  date_from,
  date_to,
  is_active,
});

describe("coverageDateGaps", () => {
  it("treats an empty plan as one gap spanning the whole window", () => {
    expect(coverageDateGaps({ ...win, periods: [] })).toEqual([
      { from: "2026-01-01", to: "2026-12-31" },
    ]);
  });

  it("surrounds a mid-year period with a leading and a trailing gap", () => {
    expect(coverageDateGaps({ ...win, periods: [period("2026-06-01", "2026-08-31")] })).toEqual([
      { from: "2026-01-01", to: "2026-05-31" },
      { from: "2026-09-01", to: "2026-12-31" },
    ]);
  });

  it("reports no gap between contiguous periods (inclusive date_to + 1 = next date_from)", () => {
    expect(
      coverageDateGaps({
        ...win,
        periods: [period("2026-01-01", "2026-06-28"), period("2026-06-29", "2026-12-31")],
      }),
    ).toEqual([]);
  });

  it("pins a single-day gap", () => {
    expect(
      coverageDateGaps({
        ...win,
        periods: [period("2026-01-01", "2026-06-27"), period("2026-06-29", "2026-12-31")],
      }),
    ).toEqual([{ from: "2026-06-28", to: "2026-06-28" }]);
  });

  it("clamps periods that spill over the year boundaries", () => {
    // Coverage runs Nov 2025 → Feb 2026 and Dec 2026 → Jan 2027: only the
    // in-window slice matters, and no gap may leak outside the window.
    expect(
      coverageDateGaps({
        ...win,
        periods: [period("2025-11-01", "2026-02-15"), period("2026-12-01", "2027-01-31")],
      }),
    ).toEqual([{ from: "2026-02-16", to: "2026-11-30" }]);
  });

  it("clamps gaps to the plan's effective range when set", () => {
    expect(
      coverageDateGaps({
        ...win,
        periods: [period("2026-06-01", "2026-07-15")],
        effectiveFrom: "2026-05-01",
        effectiveTo: "2026-09-30",
      }),
    ).toEqual([
      { from: "2026-05-01", to: "2026-05-31" },
      { from: "2026-07-16", to: "2026-09-30" },
    ]);
  });

  it("returns nothing when the effective range misses the window entirely", () => {
    expect(
      coverageDateGaps({
        ...win,
        periods: [],
        effectiveFrom: "2025-06-01",
        effectiveTo: "2025-08-31",
      }),
    ).toEqual([]);
  });

  it("returns nothing when the window is fully covered", () => {
    expect(coverageDateGaps({ ...win, periods: [period("2025-12-01", "2027-01-31")] })).toEqual([]);
  });

  it("counts inactive periods as coverage (the DB overlap EXCLUDE spans them)", () => {
    // A gap prefill must never propose dates an inactive period already owns —
    // the create would 400 on the exclusion constraint.
    expect(
      coverageDateGaps({
        ...win,
        periods: [period("2026-01-01", "2026-06-30"), period("2026-07-01", "2026-12-31", false)],
      }),
    ).toEqual([]);
  });

  it("handles unsorted and overlapping input defensively", () => {
    expect(
      coverageDateGaps({
        ...win,
        periods: [
          period("2026-09-01", "2026-12-31"),
          period("2026-01-01", "2026-05-31"),
          period("2026-05-01", "2026-06-30"),
        ],
      }),
    ).toEqual([{ from: "2026-07-01", to: "2026-08-31" }]);
  });
});
