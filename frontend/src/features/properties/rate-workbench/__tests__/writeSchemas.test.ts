import { describe, expect, it } from "vitest";
import { discountWriteInputSchema, extraWriteInputSchema, priceQuoteSchema } from "../schemas";

// A fully-valid Extra write input — the backend requires kind, calc, amount and
// the currency FK, all NOT NULL with no server default.
const validExtra = {
  name: "Transfer",
  kind: "other",
  calc: "fixed_per_stay",
  amount: "120",
  currency: 1,
};

// A fully-valid Discount write input — rule_kind, kind, amount and both validity
// dates are all required NOT NULL columns.
const validDiscount = {
  name: "Early",
  rule_kind: "early_bird",
  kind: "percent",
  amount: "10",
  // Lead-time kinds require a threshold — a null one would make the discount
  // apply to every booking (the engine skips the check when null).
  threshold_days: 60,
  valid_from: "2026-01-01",
  valid_to: "2026-03-01",
};

describe("extraWriteInputSchema", () => {
  it("accepts a complete extra and requires a name", () => {
    expect(extraWriteInputSchema.safeParse(validExtra).success).toBe(true);
    expect(extraWriteInputSchema.safeParse({ ...validExtra, name: "" }).success).toBe(false);
  });

  it("requires the backend-mandatory fields (kind, calc, amount, currency)", () => {
    for (const field of ["kind", "calc", "amount", "currency"] as const) {
      const partial = { ...validExtra };
      delete (partial as Record<string, unknown>)[field];
      expect(extraWriteInputSchema.safeParse(partial).success).toBe(false);
    }
    // A currency of 0 (the "unset" sentinel) is not a valid FK.
    expect(extraWriteInputSchema.safeParse({ ...validExtra, currency: 0 }).success).toBe(false);
  });

  it("round-trips commissionable and leaves it undefined when absent (GAP-076)", () => {
    const withFlag = extraWriteInputSchema.parse({ ...validExtra, commissionable: false });
    expect(withFlag.commissionable).toBe(false);
    const withTrue = extraWriteInputSchema.parse({ ...validExtra, commissionable: true });
    expect(withTrue.commissionable).toBe(true);
    const without = extraWriteInputSchema.parse(validExtra);
    expect(without.commissionable).toBeUndefined();
  });

  it("rejects an end date before the start date", () => {
    expect(
      extraWriteInputSchema.safeParse({
        ...validExtra,
        applies_from: "2026-08-01",
        applies_to: "2026-07-01",
      }).success,
    ).toBe(false);
    expect(
      extraWriteInputSchema.safeParse({
        ...validExtra,
        applies_from: "2026-07-01",
        applies_to: "2026-08-01",
      }).success,
    ).toBe(true);
  });
});

describe("discountWriteInputSchema", () => {
  it("accepts a complete discount and requires a name", () => {
    expect(discountWriteInputSchema.safeParse(validDiscount).success).toBe(true);
    expect(discountWriteInputSchema.safeParse({ ...validDiscount, name: "" }).success).toBe(false);
  });

  it("requires the backend-mandatory fields (rule_kind, kind, amount, dates)", () => {
    for (const field of ["rule_kind", "kind", "amount", "valid_from", "valid_to"] as const) {
      const partial = { ...validDiscount };
      delete (partial as Record<string, unknown>)[field];
      expect(discountWriteInputSchema.safeParse(partial).success).toBe(false);
    }
  });

  it("rejects a reversed validity range", () => {
    expect(
      discountWriteInputSchema.safeParse({
        ...validDiscount,
        valid_from: "2026-08-01",
        valid_to: "2026-07-01",
      }).success,
    ).toBe(false);
  });

  it("does not carry uses_count into the parsed write shape (read-only field)", () => {
    const parsed = discountWriteInputSchema.parse({ ...validDiscount, max_uses: 5 });
    expect("uses_count" in parsed).toBe(false);
  });
});

describe("priceQuoteSchema — owner economics pass through (BUG-009 fixed)", () => {
  it("keeps net_to_owner / commission / tax / price_basis at the parse boundary", () => {
    const parsed = priceQuoteSchema.parse({
      currency_code: "EUR",
      total: "1920",
      net_to_owner: "1220",
      commission: "700",
      tax: "0",
      price_basis: "gross",
      some_future_field: 42,
    }) as Record<string, unknown>;
    // The engine's figures are basis-aware and trustworthy now — the old
    // parse-boundary strip is gone.
    expect(parsed.net_to_owner).toBe("1220");
    expect(parsed.commission).toBe("700");
    expect(parsed.tax).toBe("0");
    expect(parsed.price_basis).toBe("gross");
    expect(parsed.total).toBe("1920");
    expect(parsed.some_future_field).toBe(42);
  });

  it("tolerates legacy responses without the owner fields", () => {
    const parsed = priceQuoteSchema.parse({
      currency_code: "EUR",
      total: "1920",
    }) as Record<string, unknown>;
    expect(parsed.net_to_owner).toBeUndefined();
    expect(parsed.commission).toBeUndefined();
    expect(parsed.tax).toBeUndefined();
  });
});

describe("priceQuoteSchema — reduction keys (Q-018)", () => {
  it("parses the typed before-reduction totals and per-line reduced_from", () => {
    const parsed = priceQuoteSchema.parse({
      currency_code: "EUR",
      total: "1600",
      rate_subtotal_before_reduction: "2000",
      total_before_reduction: "2000",
      lines: [
        { date: "2026-06-01", nightly: "160.00", reduced_from: "200.00" },
        { date: "2026-06-02", nightly: "160.00", reduced_from: null },
      ],
    });
    // Typed (not just passthrough) — these drive render decisions.
    expect(parsed.rate_subtotal_before_reduction).toBe("2000");
    expect(parsed.total_before_reduction).toBe("2000");
    expect(parsed.lines[0].reduced_from).toBe("200.00");
    expect(parsed.lines[1].reduced_from).toBeNull();
  });

  it("tolerates unreduced quotes: keys nullable and optional", () => {
    const withNulls = priceQuoteSchema.parse({
      total: "1920",
      rate_subtotal_before_reduction: null,
      total_before_reduction: null,
    });
    expect(withNulls.total_before_reduction).toBeNull();
    const absent = priceQuoteSchema.parse({ total: "1920" });
    expect(absent.total_before_reduction).toBeUndefined();
    expect(absent.rate_subtotal_before_reduction).toBeUndefined();
  });
});
