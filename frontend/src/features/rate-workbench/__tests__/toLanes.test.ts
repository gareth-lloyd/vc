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
    seasonDetails: [],
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

  it("clamps null (open-ended) dates to the window bounds", () => {
    const lanes = toLanes({
      ...base(),
      services: [service({ id: 9, name: "Wifi", applies_from: null, applies_to: null })],
    });
    const band = lane(lanes, "inclusions").bands[0];
    expect(band.dateFrom).toBe("2026-01-01");
    expect(band.dateTo).toBe("2027-01-01");
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
      seasonDetails: [
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
              rules: [
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

  it("takes one price per band (its own basis), never mixing nightly with weekly", () => {
    const lanes = toLanes({
      ...base(),
      seasonDetails: [
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
              rules: [
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

  it("falls back to the plan name when the period is unnamed", () => {
    const lanes = toLanes({
      ...base(),
      seasonDetails: [
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
              rules: [{ id: 1, period: 51, nightly: "650" }],
            },
          ],
        }),
      ],
    });
    expect(lane(lanes, "rates").bands[0]).toMatchObject({ id: "period-51", label: "Summer" });
  });

  it("skips periods with no rules", () => {
    const lanes = toLanes({
      ...base(),
      seasonDetails: [
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
              rules: [],
            },
          ],
        }),
      ],
    });
    expect(lane(lanes, "rates").bands).toHaveLength(0);
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
      rules: [{ id, period: id, nightly }],
    });
    const lanes = toLanes({
      ...base(),
      seasonDetails: [
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
      rules: [{ id, period: id, nightly }],
    });
    // A lone period, or two distinct prices, can't form meaningful tertiles — a
    // single period must not read as the darkest "high" tone.
    const single = toLanes({
      ...base(),
      seasonDetails: [detail({ id: 5, currency_code: "EUR", periods: [period(50, "100")] })],
    });
    expect(lane(single, "rates").bands[0].meta.priceTier).toBeUndefined();

    const twoDistinct = toLanes({
      ...base(),
      seasonDetails: [
        detail({ id: 5, currency_code: "EUR", periods: [period(50, "100"), period(51, "200")] }),
      ],
    });
    for (const b of lane(twoDistinct, "rates").bands) {
      expect(b.meta.priceTier).toBeUndefined();
    }
  });

  it("leaves all-POA rate periods untiered (fall back to lane tone)", () => {
    const lanes = toLanes({
      ...base(),
      seasonDetails: [
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
              rules: [{ id: 1, period: 50, is_poa: true }],
            },
          ],
        }),
      ],
    });
    expect(lane(lanes, "rates").bands[0].meta.priceTier).toBeUndefined();
  });
});
