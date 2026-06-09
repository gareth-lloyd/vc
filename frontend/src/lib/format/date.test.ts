import { describe, expect, it } from "vitest";
import { formatDate, formatNightRange } from "./date";

describe("formatDate", () => {
  it("formats an ISO string", () => {
    expect(formatDate("2026-05-14T10:00:00Z")).toBe("14 May 2026");
  });

  it("returns dash for null/undefined", () => {
    expect(formatDate(null)).toBe("—");
    expect(formatDate(undefined)).toBe("—");
  });

  it("returns dash for invalid input", () => {
    expect(formatDate("not-a-date")).toBe("—");
  });
});

describe("formatNightRange", () => {
  it("renders a single night without a dash", () => {
    expect(formatNightRange(new Date(2026, 6, 21), new Date(2026, 6, 21))).toBe("21 Jul 2026");
  });

  it("collapses the leading day when the range stays within one month", () => {
    expect(formatNightRange(new Date(2026, 6, 21), new Date(2026, 6, 30))).toBe("21–30 Jul 2026");
  });

  it("keeps both months when the range crosses a month boundary", () => {
    expect(formatNightRange(new Date(2026, 6, 29), new Date(2026, 7, 1))).toBe(
      "29 Jul – 1 Aug 2026",
    );
  });

  it("keeps both years when the range crosses a year boundary", () => {
    expect(formatNightRange(new Date(2026, 11, 30), new Date(2027, 0, 1))).toBe(
      "30 Dec 2026 – 1 Jan 2027",
    );
  });
});
