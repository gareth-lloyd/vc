import { describe, expect, it } from "vitest";
import { formatMoneyCompact, formatMoneyWhole } from "../money";

describe("formatMoneyWhole", () => {
  it("rounds to a whole amount with thousands grouping and a known symbol", () => {
    expect(formatMoneyWhole("20377.88", "GBP")).toBe("£20,378");
    expect(formatMoneyWhole("1400.00", "GBP")).toBe("£1,400");
  });

  it("trails an unmapped currency code after the number", () => {
    expect(formatMoneyWhole("1234.50", "AED")).toBe("1,235 AED");
  });

  it("returns an em dash for missing value or currency", () => {
    expect(formatMoneyWhole(null, "GBP")).toBe("—");
    expect(formatMoneyWhole("1400.00", null)).toBe("—");
    expect(formatMoneyWhole("not-a-number", "GBP")).toBe("—");
  });
});

describe("formatMoneyCompact", () => {
  it("renders compact notation hugging a known symbol", () => {
    expect(formatMoneyCompact("1400.00", "GBP")).toBe("£1.4K");
    expect(formatMoneyCompact("20377.88", "GBP")).toBe("£20.4K");
    expect(formatMoneyCompact("137693.12", "USD")).toBe("$137.7K");
  });

  it("leaves sub-thousand amounts unabbreviated", () => {
    expect(formatMoneyCompact("850.00", "EUR")).toBe("€850");
  });

  it("returns an em dash for missing value or currency", () => {
    expect(formatMoneyCompact(null, "GBP")).toBe("—");
    expect(formatMoneyCompact("1400.00", null)).toBe("—");
  });
});
