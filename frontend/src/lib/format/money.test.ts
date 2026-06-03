import { describe, expect, it } from "vitest";
import { formatMoney, isNonNegativeMoney, isPositiveMoney, parseMoney } from "./money";

describe("parseMoney", () => {
  it("parses numbers and decimal strings", () => {
    expect(parseMoney(1500)).toBe(1500);
    expect(parseMoney("1234.50")).toBe(1234.5);
  });

  it("tolerates en-GB thousands separators in valid grouping positions", () => {
    expect(parseMoney("1,000")).toBe(1000);
    expect(parseMoney("1,234,567.89")).toBe(1234567.89);
  });

  it("rejects ambiguous commas rather than silently mis-parsing them", () => {
    // A decimal comma (Greek/European) must not become a 100x value.
    expect(Number.isNaN(parseMoney("1000,50"))).toBe(true);
    expect(Number.isNaN(parseMoney("1,2,3"))).toBe(true);
    expect(Number.isNaN(parseMoney("1,00"))).toBe(true);
    expect(Number.isNaN(parseMoney("1.000,50"))).toBe(true);
  });

  it("returns NaN for null/undefined/empty/non-numeric", () => {
    expect(Number.isNaN(parseMoney(null))).toBe(true);
    expect(Number.isNaN(parseMoney(undefined))).toBe(true);
    expect(Number.isNaN(parseMoney(""))).toBe(true);
    expect(Number.isNaN(parseMoney("not-a-number"))).toBe(true);
  });
});

describe("isPositiveMoney", () => {
  it("is true only for finite amounts greater than zero", () => {
    expect(isPositiveMoney("1,000")).toBe(true);
    expect(isPositiveMoney("0.01")).toBe(true);
    expect(isPositiveMoney(1500)).toBe(true);
    expect(isPositiveMoney("0")).toBe(false);
    expect(isPositiveMoney("-5")).toBe(false);
    expect(isPositiveMoney("")).toBe(false);
    expect(isPositiveMoney("abc")).toBe(false);
    expect(isPositiveMoney(null)).toBe(false);
  });
});

describe("isNonNegativeMoney", () => {
  it("is true for zero or more, false for negatives and non-numbers", () => {
    expect(isNonNegativeMoney("0")).toBe(true);
    expect(isNonNegativeMoney("1,000")).toBe(true);
    expect(isNonNegativeMoney(0)).toBe(true);
    expect(isNonNegativeMoney("-5")).toBe(false);
    expect(isNonNegativeMoney("")).toBe(false);
    expect(isNonNegativeMoney("abc")).toBe(false);
    expect(isNonNegativeMoney(null)).toBe(false);
  });
});

describe("formatMoney", () => {
  it("formats GBP from a number", () => {
    expect(formatMoney(1500, "GBP")).toBe("£1,500.00");
  });

  it("formats EUR from a decimal string", () => {
    expect(formatMoney("1234.5", "EUR")).toBe("€1,234.50");
  });

  it("formats USD", () => {
    expect(formatMoney("99", "USD")).toBe("$99.00");
  });

  it("falls back to amount + code when the currency has no known symbol", () => {
    expect(formatMoney(10, "XYZ")).toBe("10.00 XYZ");
  });

  it("returns dash for null/undefined", () => {
    expect(formatMoney(null, "GBP")).toBe("—");
    expect(formatMoney(undefined, "GBP")).toBe("—");
  });

  it("returns dash for empty / non-numeric strings", () => {
    expect(formatMoney("", "GBP")).toBe("—");
    expect(formatMoney("not-a-number", "GBP")).toBe("—");
  });

  it("returns dash when currency code is missing", () => {
    expect(formatMoney(10, "")).toBe("—");
    expect(formatMoney(10, null)).toBe("—");
  });
});
