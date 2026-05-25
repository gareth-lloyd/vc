import { describe, expect, it } from "vitest";
import { formatMoney, parseMoney } from "./money";

describe("parseMoney", () => {
  it("parses numbers and decimal strings", () => {
    expect(parseMoney(1500)).toBe(1500);
    expect(parseMoney("1234.50")).toBe(1234.5);
  });

  it("returns NaN for null/undefined/empty/non-numeric", () => {
    expect(Number.isNaN(parseMoney(null))).toBe(true);
    expect(Number.isNaN(parseMoney(undefined))).toBe(true);
    expect(Number.isNaN(parseMoney(""))).toBe(true);
    expect(Number.isNaN(parseMoney("not-a-number"))).toBe(true);
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
