import { describe, expect, it } from "vitest";
import { buildMatrix, bandLabel, bandKey } from "../matrixModel";
import type { RatePeriod, RateRule } from "@/features/properties/schemas";

// GAP-056: a band is party × price only and carries its parent `period` FK; the
// dates live on the RatePeriod row, not the rule.
let ruleId = 0;
const rule = (o: Partial<RateRule>): RateRule => ({
  id: ++ruleId,
  period: 50,
  min_party: 2,
  max_party: 4,
  ...o,
});

let periodId = 0;
const period = (dateFrom: string, dateTo: string, rules: RateRule[]): RatePeriod => ({
  id: ++periodId,
  plan: 5,
  name: "",
  date_from: dateFrom,
  date_to: dateTo,
  rules,
  coverage_gaps: [],
});

describe("buildMatrix", () => {
  it("returns empty segments and bands for no periods", () => {
    const m = buildMatrix([]);
    expect(m.segments).toEqual([]);
    expect(m.bands).toEqual([]);
    expect(m.cells).toEqual([]);
  });

  it("derives union party-band columns, sorted by min party", () => {
    const m = buildMatrix([
      period("2026-06-01", "2026-06-28", [
        rule({ min_party: 5, max_party: 6 }),
        rule({ min_party: 2, max_party: 4 }),
      ]),
      // duplicate band in another period → still one column
      period("2026-08-02", "2026-08-30", [rule({ min_party: 2, max_party: 4 })]),
    ]);
    expect(m.bands.map((b) => [b.minParty, b.maxParty])).toEqual([
      [2, 4],
      [5, 6],
    ]);
  });

  it("derives one row per period, sorted by start date", () => {
    const m = buildMatrix([
      period("2026-08-02", "2026-08-30", [rule({})]),
      period("2026-06-01", "2026-06-28", [rule({})]),
    ]);
    expect(m.segments.map((s) => [s.dateFrom, s.dateTo])).toEqual([
      ["2026-06-01", "2026-06-28"],
      ["2026-08-02", "2026-08-30"],
    ]);
  });

  it("places each rule in its (period × band) cell and leaves gaps sparse", () => {
    const a = rule({ min_party: 2, max_party: 4 });
    const b = rule({ min_party: 5, max_party: 6 });
    const c = rule({ min_party: 2, max_party: 4 });
    const jun = period("2026-06-01", "2026-06-28", [a, b]);
    const aug = period("2026-08-02", "2026-08-30", [c]);
    const m = buildMatrix([jun, aug]);
    // rows: [Jun, Aug]; cols: [2-4, 5-6]
    expect(m.cells[0][0]?.rule?.id).toBe(a.id);
    expect(m.cells[0][1]?.rule?.id).toBe(b.id);
    expect(m.cells[1][0]?.rule?.id).toBe(c.id);
    // Aug × 5-6 has no rule → a fillable empty cell (rule null, coordinates kept)
    expect(m.cells[1][1].rule).toBeNull();
    expect(m.cells[1][1].fillable).toBe(true);
    expect(m.cells[1][1].periodId).toBe(aug.id);
    expect(m.cells[1][1].dateFrom).toBe("2026-08-02");
    expect(m.cells[1][1].minParty).toBe(5);
    expect(m.cells[1][1].maxParty).toBe(6);
  });

  it("carries the rule through so POA and price masking can be read off the cell", () => {
    const poa = rule({ is_poa: true, nightly: null, weekly: null });
    const m = buildMatrix([period("2026-06-01", "2026-06-28", [poa])]);
    expect(m.cells[0][0].rule?.is_poa).toBe(true);
  });

  it("marks an empty cell unfillable when another band in the same period covers its party range", () => {
    // Union columns span both periods; within a period an empty column that the
    // period's own band party-overlaps would 4xx on the bands-disjoint constraint.
    const m = buildMatrix([
      period("2026-06-01", "2026-06-30", [rule({ min_party: 2, max_party: 4 })]),
      period("2026-07-01", "2026-07-31", [rule({ min_party: 3, max_party: 5 })]),
    ]);
    // cols: [2-4, 3-5]
    const junRow = m.cells[0];
    const blocked = junRow.find((c) => c.minParty === 3 && c.maxParty === 5)!;
    expect(blocked.rule).toBeNull();
    expect(blocked.fillable).toBe(false);
    const julRow = m.cells[1];
    const blocked2 = julRow.find((c) => c.minParty === 2 && c.maxParty === 4)!;
    expect(blocked2.rule).toBeNull();
    expect(blocked2.fillable).toBe(false);
  });

  it("keeps a genuinely open cell fillable (disjoint party within the period)", () => {
    const m = buildMatrix([
      period("2026-06-01", "2026-06-28", [rule({ min_party: 2, max_party: 4 })]),
      period("2026-08-01", "2026-08-31", [rule({ min_party: 5, max_party: 6 })]),
    ]);
    // Jun × 5-6 is empty; Jun's only band is 2-4 (disjoint party) → fillable
    const junRow = m.cells.find((row) => row[0].dateFrom === "2026-06-01")!;
    const open = junRow.find((c) => c.minParty === 5 && c.maxParty === 6)!;
    expect(open.rule).toBeNull();
    expect(open.fillable).toBe(true);
  });
});

describe("key + label helpers", () => {
  it("builds stable band keys", () => {
    expect(bandKey({ minParty: 2, maxParty: 4 })).toBe("2|4");
    expect(bandKey({ minParty: null, maxParty: null })).toBe("*|*");
  });

  it("labels a party band as a numeric range, or null when unbounded (component translates)", () => {
    expect(bandLabel({ minParty: 2, maxParty: 4 })).toBe("2–4");
    expect(bandLabel({ minParty: 6, maxParty: 6 })).toBe("6");
    expect(bandLabel({ minParty: null, maxParty: null })).toBeNull();
  });
});
