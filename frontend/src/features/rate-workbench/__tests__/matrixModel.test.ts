import { describe, expect, it } from "vitest";
import { buildMatrix, bandLabel, segmentKey, bandKey } from "../matrixModel";
import type { RateCard, RateRule } from "@/features/properties/schemas";

let ruleId = 0;
const rule = (o: Partial<RateRule>): RateRule => ({
  id: ++ruleId,
  card: 50,
  date_from: "2026-06-01",
  date_to: "2026-06-28",
  min_party: 2,
  max_party: 4,
  ...o,
});

const card = (rules: RateRule[]): RateCard => ({
  id: 50,
  plan: 5,
  name: "Standard",
  rules,
});

describe("buildMatrix", () => {
  it("returns empty segments and bands for a card with no rules", () => {
    const m = buildMatrix(card([]));
    expect(m.segments).toEqual([]);
    expect(m.bands).toEqual([]);
    expect(m.cells).toEqual([]);
  });

  it("derives union party-band columns, sorted by min party", () => {
    const m = buildMatrix(
      card([
        rule({ min_party: 5, max_party: 6 }),
        rule({ min_party: 2, max_party: 4 }),
        rule({ min_party: 2, max_party: 4 }), // duplicate band → one column
      ]),
    );
    expect(m.bands.map((b) => [b.minParty, b.maxParty])).toEqual([
      [2, 4],
      [5, 6],
    ]);
  });

  it("derives distinct date-segment rows, sorted by start", () => {
    const m = buildMatrix(
      card([
        rule({ date_from: "2026-08-02", date_to: "2026-08-30" }),
        rule({ date_from: "2026-06-01", date_to: "2026-06-28" }),
        rule({ date_from: "2026-06-01", date_to: "2026-06-28" }), // duplicate segment → one row
      ]),
    );
    expect(m.segments.map((s) => [s.dateFrom, s.dateTo])).toEqual([
      ["2026-06-01", "2026-06-28"],
      ["2026-08-02", "2026-08-30"],
    ]);
  });

  it("places each rule in its (segment × band) cell and leaves gaps sparse", () => {
    const a = rule({ date_from: "2026-06-01", date_to: "2026-06-28", min_party: 2, max_party: 4 });
    const b = rule({ date_from: "2026-06-01", date_to: "2026-06-28", min_party: 5, max_party: 6 });
    const c = rule({ date_from: "2026-08-02", date_to: "2026-08-30", min_party: 2, max_party: 4 });
    const m = buildMatrix(card([a, b, c]));
    // rows: [Jun, Aug]; cols: [2-4, 5-6]
    expect(m.cells[0][0]?.rule?.id).toBe(a.id);
    expect(m.cells[0][1]?.rule?.id).toBe(b.id);
    expect(m.cells[1][0]?.rule?.id).toBe(c.id);
    // Aug × 5-6 has no rule → a fillable empty cell (rule null, coordinates kept)
    expect(m.cells[1][1].rule).toBeNull();
    expect(m.cells[1][1].fillable).toBe(true);
    expect(m.cells[1][1].dateFrom).toBe("2026-08-02");
    expect(m.cells[1][1].minParty).toBe(5);
    expect(m.cells[1][1].maxParty).toBe(6);
  });

  it("carries the rule through so POA and price masking can be read off the cell", () => {
    const poa = rule({ is_poa: true, nightly: null, weekly: null });
    const m = buildMatrix(card([poa]));
    expect(m.cells[0][0].rule?.is_poa).toBe(true);
  });

  it("marks an empty cell unfillable when another band's rule already covers it", () => {
    // A base band (2–4) across the whole season and a large-party peak band (5–8)
    // for a sub-range — legal per the backend (dates overlap, parties disjoint).
    const m = buildMatrix(
      card([
        rule({ date_from: "2026-06-01", date_to: "2026-08-31", min_party: 2, max_party: 4 }),
        rule({ date_from: "2026-07-01", date_to: "2026-07-31", min_party: 5, max_party: 8 }),
      ]),
    );
    // rows: [Jun01–Aug31, Jul01–Jul31]; cols: [2-4, 5-8]
    // Jun01–Aug31 × 5-8 is empty but overlaps the peak rule (dates + party) → blocked
    const baseRow = m.cells[0];
    const blocked = baseRow.find((c) => c.minParty === 5 && c.maxParty === 8)!;
    expect(blocked.rule).toBeNull();
    expect(blocked.fillable).toBe(false);
    // Jul01–Jul31 × 2-4 is empty but overlaps the base rule → blocked
    const peakRow = m.cells[1];
    const blocked2 = peakRow.find((c) => c.minParty === 2 && c.maxParty === 4)!;
    expect(blocked2.rule).toBeNull();
    expect(blocked2.fillable).toBe(false);
  });

  it("keeps a genuinely open cell fillable (disjoint dates and party)", () => {
    const m = buildMatrix(
      card([
        rule({ date_from: "2026-06-01", date_to: "2026-06-28", min_party: 2, max_party: 4 }),
        rule({ date_from: "2026-08-01", date_to: "2026-08-31", min_party: 5, max_party: 6 }),
      ]),
    );
    // Jun × 5-6 is empty; the only 5-6 rule is in Aug (disjoint dates) → fillable
    const junRow = m.cells.find((row) => row[0].dateFrom === "2026-06-01")!;
    const open = junRow.find((c) => c.minParty === 5 && c.maxParty === 6)!;
    expect(open.rule).toBeNull();
    expect(open.fillable).toBe(true);
  });
});

describe("key + label helpers", () => {
  it("builds stable segment and band keys", () => {
    expect(segmentKey({ dateFrom: "2026-06-01", dateTo: "2026-06-28" })).toBe(
      "2026-06-01|2026-06-28",
    );
    expect(bandKey({ minParty: 2, maxParty: 4 })).toBe("2|4");
    expect(bandKey({ minParty: null, maxParty: null })).toBe("*|*");
  });

  it("labels a party band as a numeric range, or null when unbounded (component translates)", () => {
    expect(bandLabel({ minParty: 2, maxParty: 4 })).toBe("2–4");
    expect(bandLabel({ minParty: 6, maxParty: 6 })).toBe("6");
    expect(bandLabel({ minParty: null, maxParty: null })).toBeNull();
  });
});
