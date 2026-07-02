import { describe, expect, it } from "vitest";
import {
  checkedSaveableBands,
  isStagedLineValid,
  lineEffectiveTotal,
  stagedLineErrors,
} from "../lineTotals";
import { type StagedBand, type StagedLine, stagedLineId } from "../schemas";

function stagedLine(overrides: Partial<StagedLine> = {}): StagedLine {
  const base = {
    property_id: 7,
    property_name: "Villa Sol",
    hero_image_url: null,
    date_from: "2026-07-01",
    date_to: "2026-07-08",
    priced_date_from: "2026-07-01",
    priced_date_to: "2026-07-08",
    adults: 2,
    children: 0,
    currency: "USD",
    total: "4500.00",
    discount: "0",
    inclusions: "",
    price_override_reason: "",
    is_manual: false,
    manual_only: false,
    notes: "",
    ...overrides,
  };
  return { line_id: stagedLineId(base.property_id, base.date_from), ...base };
}

function band(overrides: Partial<StagedBand> = {}): StagedBand {
  return {
    min_party: 1,
    max_party: 4,
    adults: 4,
    total: "4500.00",
    currency: "USD",
    is_poa: false,
    checked: true,
    ...overrides,
  };
}

describe("lineTotals — banded lines (GAP-044)", () => {
  it("gives a banded line no single effective total (bands are alternatives)", () => {
    const line = stagedLine({ total: null, occupancy_bands: [band(), band({ adults: 6 })] });
    expect(lineEffectiveTotal(line)).toBeNull();
  });

  it("checkedSaveableBands keeps only checked, non-POA, priced bands", () => {
    const line = stagedLine({
      total: null,
      occupancy_bands: [
        band({ adults: 4 }), // checked, priced → kept
        band({ adults: 6, checked: false }), // unchecked → dropped
        band({ adults: 8, is_poa: true, total: null }), // POA → dropped
        band({ adults: 10, total: null }), // no total → dropped
      ],
    });
    const saveable = checkedSaveableBands(line);
    expect(saveable).toHaveLength(1);
    expect(saveable[0].adults).toBe(4);
  });

  it("is invalid when no non-POA band is checked, valid with at least one", () => {
    const noneChecked = stagedLine({
      total: null,
      occupancy_bands: [band({ checked: false }), band({ is_poa: true, total: null })],
    });
    expect(isStagedLineValid(noneChecked)).toBe(false);
    expect(stagedLineErrors(noneChecked).total).toBe("quotations:schema_errors.bands_none_checked");

    const oneChecked = stagedLine({
      total: null,
      occupancy_bands: [band({ checked: true }), band({ checked: false })],
    });
    expect(isStagedLineValid(oneChecked)).toBe(true);
    expect(stagedLineErrors(oneChecked)).toEqual({});
  });
});
