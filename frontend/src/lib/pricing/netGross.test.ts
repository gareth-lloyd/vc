import { describe, expect, it } from "vitest";
import { deriveNetGross, roundHalfEven, type CommissionInput, type TaxInput } from "./netGross";

const pctCommission = (amount: string): CommissionInput => ({
  calculation_type: "percent",
  amount,
});
const fixedCommission = (amount: string): CommissionInput => ({
  calculation_type: "fixed",
  amount,
});
const tax = (percentage: string, is_exempt = false): TaxInput => ({ percentage, is_exempt });
const noTax: TaxInput = { percentage: "0", is_exempt: true };

describe("deriveNetGross — GROSS basis (carve out owner net)", () => {
  it("carves a percentage commission out of the gross", () => {
    // gross 1000, 20% commission, no tax → net 800
    const result = deriveNetGross(1000, "gross", pctCommission("20.00"), noTax);
    expect(result).toEqual({ counterpart: 800, commission: 200, tax: 0 });
  });

  it("carves commission off the post-tax remainder, taxing the gross", () => {
    // gross 1000, 10% tax, 20% commission of the post-tax 900 → tax 100, comm 180, net 720
    const result = deriveNetGross(1000, "gross", pctCommission("20.00"), tax("10.00"));
    expect(result).toEqual({ counterpart: 720, commission: 180, tax: 100 });
  });

  it("subtracts a fixed commission flat", () => {
    // gross 1200, fixed 500, no tax → net 700
    const result = deriveNetGross(1200, "gross", fixedCommission("500.00"), noTax);
    expect(result).toEqual({ counterpart: 700, commission: 500, tax: 0 });
  });

  it("skips tax entirely when the policy is exempt", () => {
    // 13% rate present but exempt → behaves as if tax were 0
    const result = deriveNetGross(1000, "gross", pctCommission("20.00"), tax("13.00", true));
    expect(result).toEqual({ counterpart: 800, commission: 200, tax: 0 });
  });
});

describe("deriveNetGross — NET basis (gross up to guest total)", () => {
  it("grosses up a percentage commission (÷(1−pct), not ×(1+pct))", () => {
    // net 800, 20% commission → commission 200, total 1000 (800/0.8)
    const result = deriveNetGross(800, "net", pctCommission("20.00"), noTax);
    expect(result).toEqual({ counterpart: 1000, commission: 200, tax: 0 });
  });

  it("grosses up commission then tax on net+commission", () => {
    // net 720, 20% comm → 180; tax base 900, 10% tax → 100; total 1000
    const result = deriveNetGross(720, "net", pctCommission("20.00"), tax("10.00"));
    expect(result).toEqual({ counterpart: 1000, commission: 180, tax: 100 });
  });

  it("adds a fixed commission flat", () => {
    // net 700, fixed 500 → total 1200
    const result = deriveNetGross(700, "net", fixedCommission("500.00"), noTax);
    expect(result).toEqual({ counterpart: 1200, commission: 500, tax: 0 });
  });
});

describe("deriveNetGross — round trips (gross ⇄ net are inverses)", () => {
  it("net→gross→net recovers the original (commission + tax)", () => {
    const up = deriveNetGross(720, "net", pctCommission("20.00"), tax("10.00"));
    expect(up?.counterpart).toBe(1000);
    const down = deriveNetGross(1000, "gross", pctCommission("20.00"), tax("10.00"));
    expect(down?.counterpart).toBe(720);
  });
});

describe("deriveNetGross — degenerate inputs return null", () => {
  it("returns null for empty / zero / unparseable / POA-masked amounts", () => {
    expect(deriveNetGross("", "gross", pctCommission("20.00"), noTax)).toBeNull();
    expect(deriveNetGross(0, "gross", pctCommission("20.00"), noTax)).toBeNull();
    expect(deriveNetGross(null, "net", pctCommission("20.00"), noTax)).toBeNull();
    expect(deriveNetGross("abc", "net", pctCommission("20.00"), noTax)).toBeNull();
  });

  it("returns null when a NET gross-up would divide by zero (≥100%)", () => {
    expect(deriveNetGross(800, "net", pctCommission("100.00"), noTax)).toBeNull();
    expect(deriveNetGross(800, "net", pctCommission("20.00"), tax("100.00"))).toBeNull();
  });

  it("treats a missing commission/tax config as zero", () => {
    const result = deriveNetGross(1000, "gross", null, null);
    expect(result).toEqual({ counterpart: 1000, commission: 0, tax: 0 });
  });
});

describe("roundHalfEven — matches the backend quantise_money policy", () => {
  it("rounds halves to the even neighbour", () => {
    expect(roundHalfEven(50.005)).toBe(50.0); // .005 → .00 (0 is even)
    expect(roundHalfEven(50.015)).toBe(50.02); // .015 → .02 (2 is even)
    expect(roundHalfEven(50.025)).toBe(50.02); // .025 → .02 (2 is even)
  });

  it("rounds non-halves normally and handles negatives symmetrically", () => {
    expect(roundHalfEven(50.024)).toBe(50.02);
    expect(roundHalfEven(50.026)).toBe(50.03);
    expect(roundHalfEven(-50.015)).toBe(-50.02);
  });

  it("applies banker's rounding through the derivation", () => {
    // gross 100.03, 50% commission, no tax: commission 50.015 → 50.02,
    // net 100.03 − 50.015 = 50.015 → 50.02
    const result = deriveNetGross(100.03, "gross", pctCommission("50.00"), noTax);
    expect(result).toEqual({ counterpart: 50.02, commission: 50.02, tax: 0 });
  });
});
