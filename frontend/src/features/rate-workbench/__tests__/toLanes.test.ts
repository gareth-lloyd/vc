import { describe, expect, it } from "vitest";
import { toLanes, type LaneKey, type LaneModel, type ToLanesInput } from "../toLanes";
import { yearWindowFor } from "../yearWindow";
import type {
  ChangeOverRule,
  Discount,
  Extra,
  PropertyService,
  RatePlan,
  RatePlanDetail,
} from "@/features/properties/schemas";

const win = yearWindowFor(2026);

function base(): ToLanesInput {
  return {
    windowStart: win.windowStart,
    dayCount: win.dayCount,
    windowFrom: win.from,
    windowTo: win.to,
    seasons: [],
    ratePlanDetails: [],
    services: [],
    extras: [],
    discounts: [],
    changeover: [],
  };
}

const season = (o: Partial<RatePlan>): RatePlan => ({ id: 1, property: 7, name: "S", ...o });
const service = (o: Partial<PropertyService>): PropertyService => ({
  id: 1,
  property: 7,
  name: "Svc",
  copy: "copy",
  sort_order: 0,
  is_active: true,
  ...o,
});
const extra = (o: Partial<Extra>): Extra => ({ id: 1, property: 7, name: "X", ...o });
const detail = (o: Partial<RatePlanDetail>): RatePlanDetail => ({
  id: 1,
  property: 7,
  name: "P",
  periods: [],
  ...o,
});

const lane = (lanes: LaneModel[], key: LaneKey) => lanes.find((l) => l.key === key)!;

describe("toLanes", () => {
  it("returns the six lanes in order, all empty for empty input", () => {
    const lanes = toLanes(base());
    expect(lanes.map((l) => l.key)).toEqual([
      "seasons",
      "rates",
      "inclusions",
      "extras",
      "discounts",
      "changeover",
    ]);
    expect(lanes.every((l) => l.bands.length === 0)).toBe(true);
  });

  it("maps a season to a band using its effective dates", () => {
    const lanes = toLanes({
      ...base(),
      seasons: [
        season({
          id: 1,
          name: "Summer 2026",
          effective_from: "2026-06-01",
          effective_to: "2026-08-31",
          currency_code: "EUR",
        }),
      ],
    });
    expect(lane(lanes, "seasons").bands[0]).toMatchObject({
      id: "season-1",
      laneKey: "seasons",
      dateFrom: "2026-06-01",
      dateTo: "2026-08-31",
      label: "Summer 2026",
      sourceId: 1,
      sublane: 0,
    });
  });

  it("clamps null (open-ended) dates to the window's inclusive bounds", () => {
    const lanes = toLanes({
      ...base(),
      services: [service({ id: 9, name: "Wifi", applies_from: null, applies_to: null })],
    });
    const band = lane(lanes, "inclusions").bands[0];
    expect(band.dateFrom).toBe("2026-01-01");
    // Band dates are inclusive, so the substitute is the year's LAST day —
    // display sites must never announce next Jan 1 as an included date.
    expect(band.dateTo).toBe("2026-12-31");
    expect(band.dateToExclusive).toBe("2027-01-01");
  });

  it("drops bands that fall entirely outside the window", () => {
    const lanes = toLanes({
      ...base(),
      seasons: [season({ id: 1, effective_from: "2025-01-01", effective_to: "2025-12-31" })],
    });
    expect(lane(lanes, "seasons").bands).toHaveLength(0);
  });

  it("stacks overlapping bands onto separate sub-lanes", () => {
    const lanes = toLanes({
      ...base(),
      extras: [
        extra({ id: 1, name: "A", applies_from: "2026-06-01", applies_to: "2026-07-01" }),
        extra({ id: 2, name: "B", applies_from: "2026-06-15", applies_to: "2026-07-15" }),
        extra({ id: 3, name: "C", applies_from: "2026-09-01", applies_to: "2026-09-30" }),
      ],
    });
    const bySource = Object.fromEntries(
      lane(lanes, "extras").bands.map((b) => [b.sourceId, b.sublane]),
    );
    expect(bySource[1]).toBe(0);
    expect(bySource[2]).toBe(1); // overlaps A → second sub-lane
    expect(bySource[3]).toBe(0); // disjoint from A → reuses first sub-lane
  });

  it("derives a rate band from a period, ranging price across its bands (GAP-056)", () => {
    const lanes = toLanes({
      ...base(),
      ratePlanDetails: [
        detail({
          id: 5,
          name: "Summer",
          currency_code: "EUR",
          periods: [
            {
              id: 50,
              plan: 5,
              name: "Standard",
              // The period owns the dates; its bands are party × price only.
              date_from: "2026-06-01",
              date_to: "2026-08-30",
              coverage_gaps: [],
              bands: [
                { id: 1, period: 50, nightly: "650" },
                { id: 2, period: 50, nightly: "900" },
                { id: 3, period: 50, is_poa: true },
              ],
            },
          ],
        }),
      ],
    });
    const band = lane(lanes, "rates").bands[0];
    expect(band).toMatchObject({
      id: "period-50",
      dateFrom: "2026-06-01",
      dateTo: "2026-08-30",
      label: "Standard",
      sourceId: 50,
    });
    expect(band.meta).toMatchObject({
      planName: "Summer",
      minPrice: 650,
      maxPrice: 900,
      hasPoa: true,
    });
  });

  it("computes addAfter per period: suppressed when contiguous, capped at the next period, open for the last", () => {
    const period = (id: number, date_from: string, date_to: string) => ({
      id,
      plan: 5,
      name: `p${id}`,
      date_from,
      date_to,
      coverage_gaps: [],
      bands: [],
    });
    const lanes = toLanes({
      ...base(),
      ratePlanDetails: [
        detail({
          id: 5,
          name: "Summer",
          periods: [
            // Deliberately unsorted: neighbour lookup must not rely on order.
            period(52, "2026-08-10", "2026-08-31"),
            period(50, "2026-06-01", "2026-06-28"),
            period(51, "2026-06-29", "2026-07-26"),
          ],
        }),
      ],
    });
    const meta = (id: number) => lane(lanes, "rates").bands.find((b) => b.sourceId === id)!.meta;
    // 51 starts the day after 50 ends → nothing can be created between them.
    expect(meta(50).addAfter).toBeUndefined();
    // Gap between 51 and 52 → prefill spans exactly the free range.
    expect(meta(51).addAfter).toEqual({ date_from: "2026-07-27", date_to: "2026-08-09" });
    // No successor → open-ended prefill (dialog suggests the end).
    expect(meta(52).addAfter).toEqual({ date_from: "2026-09-01" });
  });

  it("suppresses addAfter for periods running past the window, keeps it at the exact edge", () => {
    const period = (id: number, date_from: string, date_to: string) => ({
      id,
      plan: 5,
      name: `p${id}`,
      date_from,
      date_to,
      coverage_gaps: [],
      bands: [],
    });
    const lanes = toLanes({
      ...base(),
      ratePlanDetails: [
        detail({
          id: 5,
          name: "Winter",
          periods: [
            // Ends beyond the 2026 window: the band renders clamped at Dec 31,
            // so a "+" there would sit mid-period — no prefill.
            period(50, "2026-11-01", "2027-02-25"),
          ],
        }),
        detail({
          id: 6,
          name: "Year-end",
          // Ends exactly on the window's last day: the true end IS visible.
          periods: [period(60, "2026-10-01", "2026-12-31")],
        }),
      ],
    });
    const meta = (id: number) => lane(lanes, "rates").bands.find((b) => b.sourceId === id)!.meta;
    expect(meta(50).addAfter).toBeUndefined();
    expect(meta(60).addAfter).toEqual({ date_from: "2027-01-01" });
  });

  it("scopes addAfter neighbours to the owning plan, ignoring other plans' periods", () => {
    const period = (id: number, plan: number, date_from: string, date_to: string) => ({
      id,
      plan,
      name: `p${id}`,
      date_from,
      date_to,
      coverage_gaps: [],
      bands: [],
    });
    const lanes = toLanes({
      ...base(),
      ratePlanDetails: [
        detail({ id: 5, name: "A", periods: [period(50, 5, "2026-06-01", "2026-06-28")] }),
        // Plan B prices the day right after plan A's period — must not suppress A's "+".
        detail({ id: 6, name: "B", periods: [period(60, 6, "2026-06-29", "2026-07-26")] }),
      ],
    });
    const meta = (id: number) => lane(lanes, "rates").bands.find((b) => b.sourceId === id)!.meta;
    expect(meta(50).addAfter).toEqual({ date_from: "2026-06-29" });
    expect(meta(60).addAfter).toEqual({ date_from: "2026-07-27" });
  });

  it("takes one price per band (its own basis), never mixing nightly with weekly", () => {
    const lanes = toLanes({
      ...base(),
      ratePlanDetails: [
        detail({
          id: 5,
          currency_code: "EUR",
          periods: [
            {
              id: 50,
              plan: 5,
              name: "Standard",
              date_from: "2026-06-01",
              date_to: "2026-08-02",
              coverage_gaps: [],
              bands: [
                // nightly present → weekly on the same band must be ignored,
                // else the €4,550/wk figure would blow the range out.
                { id: 1, period: 50, nightly: "650", weekly: "4550" },
                { id: 2, period: 50, nightly: "900" },
              ],
            },
          ],
        }),
      ],
    });
    expect(lane(lanes, "rates").bands[0].meta).toMatchObject({ minPrice: 650, maxPrice: 900 });
  });

  it("falls back to the compact date span when the period is unnamed (GAP-059)", () => {
    const lanes = toLanes({
      ...base(),
      ratePlanDetails: [
        detail({
          id: 5,
          name: "Summer",
          periods: [
            {
              id: 51,
              plan: 5,
              date_from: "2026-06-01",
              date_to: "2026-06-30",
              coverage_gaps: [],
              bands: [{ id: 1, period: 51, nightly: "650" }],
            },
          ],
        }),
      ],
    });
    expect(lane(lanes, "rates").bands[0]).toMatchObject({ id: "period-51", label: "1–30 Jun" });
  });

  it("keeps zero-band periods visible, flagged noRates (not silently dropped)", () => {
    const lanes = toLanes({
      ...base(),
      ratePlanDetails: [
        detail({
          id: 5,
          periods: [
            {
              id: 50,
              plan: 5,
              name: "Empty",
              date_from: "2026-06-01",
              date_to: "2026-06-30",
              coverage_gaps: [],
              bands: [],
            },
          ],
        }),
      ],
    });
    const band = lane(lanes, "rates").bands[0];
    expect(band).toMatchObject({ id: "period-50", label: "Empty" });
    expect(band.meta).toMatchObject({ noRates: true, minPrice: null, hasPoa: false });
  });

  it("keeps a single-day band visible (dates are inclusive, so one day has width)", () => {
    const lanes = toLanes({
      ...base(),
      seasons: [season({ id: 1, effective_from: "2026-06-01", effective_to: "2026-06-01" })],
    });
    expect(lane(lanes, "seasons").bands).toHaveLength(1);
  });

  it("stacks bands that share only their boundary day (inclusive overlap)", () => {
    // A ends Jul 1 and B starts Jul 1: both price Jul 1, so they overlap and
    // must stack — treating the inclusive date_to as an exclusive edge used to
    // let them share a sub-lane.
    const lanes = toLanes({
      ...base(),
      extras: [
        extra({ id: 1, name: "A", applies_from: "2026-06-01", applies_to: "2026-07-01" }),
        extra({ id: 2, name: "B", applies_from: "2026-07-01", applies_to: "2026-07-15" }),
      ],
    });
    const bySource = Object.fromEntries(
      lane(lanes, "extras").bands.map((b) => [b.sourceId, b.sublane]),
    );
    expect(bySource[1]).toBe(0);
    expect(bySource[2]).toBe(1);
  });

  it("labels a changeover band with its weekday and required dates", () => {
    const changeover: ChangeOverRule = {
      id: 3,
      property: 7,
      weekday: "sat",
      effective_from: "2026-06-01",
      effective_to: "2026-08-31",
    };
    const discount: Discount = {
      id: 4,
      property: 7,
      name: "Early",
      code: "E",
      kind: "percent",
    };
    const lanes = toLanes({ ...base(), changeover: [changeover], discounts: [discount] });
    expect(lane(lanes, "changeover").bands[0]).toMatchObject({
      sourceId: 3,
      meta: { weekday: "sat" },
    });
    expect(lane(lanes, "discounts").bands[0]).toMatchObject({
      sourceId: 4,
      meta: { code: "E", kind: "percent" },
    });
  });

  it("ranks rate periods into global price tiers across all plans (not per-plan)", () => {
    const period = (id: number, nightly: string) => ({
      id,
      plan: 0,
      name: `P${id}`,
      date_from: "2026-06-01",
      date_to: "2026-08-31",
      coverage_gaps: [],
      bands: [{ id, period: id, nightly }],
    });
    const lanes = toLanes({
      ...base(),
      ratePlanDetails: [
        // Two separate single-period plans + one two-period plan: a per-plan
        // ranking would make each single-period plan uniformly one tier. Global
        // tertiles over [100, 200, 300] give low / mid / high regardless of
        // grouping.
        detail({ id: 5, name: "A", currency_code: "EUR", periods: [period(50, "100")] }),
        detail({ id: 6, name: "B", currency_code: "EUR", periods: [period(60, "300")] }),
        detail({ id: 7, name: "C", currency_code: "EUR", periods: [period(70, "200")] }),
      ],
    });
    const tierBySource = Object.fromEntries(
      lane(lanes, "rates").bands.map((b) => [b.sourceId, b.meta.priceTier]),
    );
    expect(tierBySource[50]).toBe("low");
    expect(tierBySource[70]).toBe("mid");
    expect(tierBySource[60]).toBe("high");
  });

  it("leaves rate periods untiered when there are fewer than three distinct prices", () => {
    const period = (id: number, nightly: string) => ({
      id,
      plan: 0,
      name: `P${id}`,
      date_from: "2026-06-01",
      date_to: "2026-08-31",
      coverage_gaps: [],
      bands: [{ id, period: id, nightly }],
    });
    // A lone period, or two distinct prices, can't form meaningful tertiles — a
    // single period must not read as the darkest "high" tone.
    const single = toLanes({
      ...base(),
      ratePlanDetails: [detail({ id: 5, currency_code: "EUR", periods: [period(50, "100")] })],
    });
    expect(lane(single, "rates").bands[0].meta.priceTier).toBeUndefined();

    const twoDistinct = toLanes({
      ...base(),
      ratePlanDetails: [
        detail({ id: 5, currency_code: "EUR", periods: [period(50, "100"), period(51, "200")] }),
      ],
    });
    for (const b of lane(twoDistinct, "rates").bands) {
      expect(b.meta.priceTier).toBeUndefined();
    }
  });

  it("inserts a coverage lane for the selected plan, with inclusive gap bands", () => {
    const lanes = toLanes({
      ...base(),
      coveragePlanId: 5,
      ratePlanDetails: [
        detail({
          id: 5,
          name: "Summer",
          effective_from: "2026-05-01",
          effective_to: "2026-09-30",
          periods: [
            {
              id: 50,
              plan: 5,
              name: "Standard",
              date_from: "2026-06-01",
              date_to: "2026-08-31",
              coverage_gaps: [],
              bands: [{ id: 1, period: 50, nightly: "650" }],
            },
          ],
        }),
      ],
    });
    // Positioned directly under the rates lane it annotates.
    expect(lanes.map((l) => l.key)).toEqual([
      "seasons",
      "rates",
      "coverage",
      "inclusions",
      "extras",
      "discounts",
      "changeover",
    ]);
    const coverage = lane(lanes, "coverage");
    expect(coverage.planName).toBe("Summer");
    expect(coverage.bands).toHaveLength(2);
    expect(coverage.bands[0]).toMatchObject({
      dateFrom: "2026-05-01",
      dateTo: "2026-05-31",
      sourceId: 5,
      meta: { isGap: true, planName: "Summer" },
    });
    expect(coverage.bands[1]).toMatchObject({
      dateFrom: "2026-09-01",
      dateTo: "2026-09-30",
    });
  });

  it("includes an empty coverage lane when the selected plan is fully covered", () => {
    const lanes = toLanes({
      ...base(),
      coveragePlanId: 5,
      ratePlanDetails: [
        detail({
          id: 5,
          name: "Summer",
          effective_from: "2026-06-01",
          effective_to: "2026-08-31",
          periods: [
            {
              id: 50,
              plan: 5,
              date_from: "2026-06-01",
              date_to: "2026-08-31",
              coverage_gaps: [],
              bands: [{ id: 1, period: 50, nightly: "650" }],
            },
          ],
        }),
      ],
    });
    // Present but empty — "no gaps" is positive feedback, not a missing lane.
    expect(lane(lanes, "coverage").bands).toHaveLength(0);
  });

  it("omits the coverage lane when no plan is selected or its detail is not loaded", () => {
    expect(toLanes(base()).some((l) => l.key === "coverage")).toBe(false);
    expect(toLanes({ ...base(), coveragePlanId: 99 }).some((l) => l.key === "coverage")).toBe(
      false,
    );
  });

  it("omits the coverage lane when the plan's effective range misses the window", () => {
    // An empty lane would falsely read "no gaps" for a year the plan never
    // prices — the lane only appears when the plan touches the window.
    const lanes = toLanes({
      ...base(),
      coveragePlanId: 5,
      ratePlanDetails: [
        detail({
          id: 5,
          name: "Summer 2025",
          effective_from: "2025-06-01",
          effective_to: "2025-08-31",
          periods: [],
        }),
      ],
    });
    expect(lanes.some((l) => l.key === "coverage")).toBe(false);
  });

  it("leaves all-POA rate periods untiered (fall back to lane tone)", () => {
    const lanes = toLanes({
      ...base(),
      ratePlanDetails: [
        detail({
          id: 5,
          name: "A",
          currency_code: "EUR",
          periods: [
            {
              id: 50,
              plan: 5,
              name: "POA",
              date_from: "2026-06-01",
              date_to: "2026-08-31",
              coverage_gaps: [],
              bands: [{ id: 1, period: 50, is_poa: true }],
            },
          ],
        }),
      ],
    });
    expect(lane(lanes, "rates").bands[0].meta.priceTier).toBeUndefined();
  });
});
