import { describe, expect, it } from "vitest";
import type { BandMeta, LaneKey, WorkbenchBand } from "../toLanes";
import { TONE_CLASS, bandToneClass } from "../components/timelineLayout";

const band = (laneKey: LaneKey, meta: BandMeta = {}): WorkbenchBand => ({
  id: "b",
  laneKey,
  dateFrom: "2026-01-01",
  dateTo: "2026-02-01",
  dateToExclusive: "2026-02-02",
  label: "B",
  sourceId: 1,
  sublane: 0,
  meta,
});

describe("bandToneClass", () => {
  it("colours rate bands by price tier, distinct per tier", () => {
    const low = bandToneClass(band("rates", { priceTier: "low" }));
    const mid = bandToneClass(band("rates", { priceTier: "mid" }));
    const high = bandToneClass(band("rates", { priceTier: "high" }));
    expect(new Set([low, mid, high]).size).toBe(3);
  });

  it("falls back to the lane tone for untiered (all-POA) rate bands", () => {
    expect(bandToneClass(band("rates", {}))).toBe(TONE_CLASS.rates);
  });

  it("emphasises mandatory extras more strongly than optional ones", () => {
    const mandatory = bandToneClass(band("extras", { isMandatory: true }));
    const optional = bandToneClass(band("extras", { isMandatory: false }));
    expect(mandatory).not.toBe(optional);
  });

  it("uses the flat lane tone for other lanes", () => {
    expect(bandToneClass(band("seasons"))).toBe(TONE_CLASS.seasons);
    expect(bandToneClass(band("inclusions"))).toBe(TONE_CLASS.inclusions);
    expect(bandToneClass(band("discounts"))).toBe(TONE_CLASS.discounts);
    expect(bandToneClass(band("changeover"))).toBe(TONE_CLASS.changeover);
  });
});
