import { describe, expect, it } from "vitest";
import {
  addDaysIso,
  formatDate,
  formatNightRange,
  formatWeekRangeCompact,
  suggestRateBandEnd,
  toDatetimeLocal,
} from "./date";

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

describe("formatWeekRangeCompact", () => {
  // Formats the two ISO endpoints DIRECTLY (checkout semantics): a block
  // running 1 Aug → 8 Aug reads "1–8 Aug", not "1–7". No year within one year;
  // year(s) only when the range crosses a year boundary.
  it("collapses the leading day when both endpoints share a month", () => {
    expect(formatWeekRangeCompact("2026-08-01", "2026-08-08")).toBe("1–8 Aug");
  });

  it("keeps both months when the endpoints cross a month boundary", () => {
    expect(formatWeekRangeCompact("2026-07-25", "2026-08-01")).toBe("25 Jul–1 Aug");
  });

  it("includes both years when the endpoints cross a year boundary", () => {
    expect(formatWeekRangeCompact("2026-12-27", "2027-01-03")).toBe("27 Dec 2026–3 Jan 2027");
  });

  it("returns a dash for empty or unparseable endpoints", () => {
    expect(formatWeekRangeCompact("", "2026-08-08")).toBe("—");
    expect(formatWeekRangeCompact("2026-08-01", "not-a-date")).toBe("—");
  });
});

describe("toDatetimeLocal", () => {
  it("renders a Date as the local datetime-local input shape", () => {
    expect(toDatetimeLocal(new Date(2026, 5, 11, 9, 5))).toBe("2026-06-11T09:05");
  });

  it("converts a UTC ISO string to local wall-clock", () => {
    const iso = "2026-06-18T20:59:59Z";
    const expected = new Date(iso);
    const pad = (n: number) => String(n).padStart(2, "0");
    expect(toDatetimeLocal(iso)).toBe(
      `${expected.getFullYear()}-${pad(expected.getMonth() + 1)}-${pad(expected.getDate())}T${pad(expected.getHours())}:${pad(expected.getMinutes())}`,
    );
  });
});

describe("addDaysIso", () => {
  it("adds a day within a month", () => {
    expect(addDaysIso("2026-06-08", 1)).toBe("2026-06-09");
  });

  it("rolls over month and year boundaries", () => {
    expect(addDaysIso("2026-07-31", 1)).toBe("2026-08-01");
    expect(addDaysIso("2026-12-31", 1)).toBe("2027-01-01");
  });
});

describe("suggestRateBandEnd", () => {
  // 2026-07-04 is a Saturday.
  it("ends the day before the next changeover for a same-weekday start", () => {
    // Sat → 7-night min: next Sat changeover is 11 Jul, so date_to is Fri 10 Jul.
    expect(suggestRateBandEnd("2026-07-04", "sat", 7)).toBe("2026-07-10");
  });

  it("wraps across the week boundary when the start isn't the changeover day", () => {
    // 2026-07-08 is a Wednesday; Sat changeover ≥ 7 nights → next Sat is 18 Jul,
    // so date_to is Fri 17 Jul (10 days out).
    expect(suggestRateBandEnd("2026-07-08", "sat", 7)).toBe("2026-07-17");
  });

  it("respects a minimum longer than a week", () => {
    // Sat start, 10-night min: the first Sat changeover ≥ 10 days out is 14 days
    // (18 Jul), so date_to is Fri 17 Jul.
    expect(suggestRateBandEnd("2026-07-04", "sat", 10)).toBe("2026-07-17");
  });

  it("defaults to a sensible minimum when minNights is missing or non-positive", () => {
    expect(suggestRateBandEnd("2026-07-04", "sat", null)).toBe("2026-07-10");
    expect(suggestRateBandEnd("2026-07-04", "sat", 0)).toBe("2026-07-10");
  });

  it("returns null when there is no fixed changeover day", () => {
    expect(suggestRateBandEnd("2026-07-04", "any", 7)).toBeNull();
    expect(suggestRateBandEnd("2026-07-04", null, 7)).toBeNull();
    expect(suggestRateBandEnd("2026-07-04", undefined, 7)).toBeNull();
  });

  it("returns null for empty or unparseable start dates", () => {
    expect(suggestRateBandEnd("", "sat", 7)).toBeNull();
    expect(suggestRateBandEnd("not-a-date", "sat", 7)).toBeNull();
  });
});
