import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/render";
import type { PriceQuote } from "../schemas";
import { QuoteResultCard } from "../components/QuoteResultCard";

// A GROSS-plan quote from the live probe: the engine inflates `total` by adding
// commission on top (BUG-009), so its own lines (3045 + 150) sum to 3195 while
// `total` reads 3690.22. Owner economics are already stripped at the schema
// boundary, so they never appear on the object we build here.
const grossQuote: PriceQuote = {
  currency_code: "GBP",
  party: 2,
  lines: [
    { date: "2026-07-11", nightly: "435" },
    { date: "2026-07-12", nightly: "435" },
  ],
  rate_subtotal: "3045",
  extras: [],
  extras_total: "150",
  discount: "0",
  total: "3690.22",
  plan_id: 35,
  winning_period_id: null,
  is_projected: false,
  occupancy_pricing: false,
};

describe("QuoteResultCard", () => {
  it("gross: guest total reconciles with the shown lines (rate + extras − discount)", () => {
    renderWithProviders(<QuoteResultCard quote={grossQuote} basis="gross" />);
    // 3045 + 150 − 0 = 3195, NOT the engine's inflated 3690.22.
    expect(screen.getByText("Guest total")).toBeInTheDocument();
    expect(screen.getByText("£3,195.00")).toBeInTheDocument();
    expect(screen.queryByText("£3,690.22")).toBeNull();
    // No reconciling taxes/fees line under gross.
    expect(screen.queryByText("Taxes & fees")).toBeNull();
  });

  it("defaults to gross when no basis is supplied", () => {
    renderWithProviders(<QuoteResultCard quote={grossQuote} />);
    expect(screen.getByText("£3,195.00")).toBeInTheDocument();
    expect(screen.queryByText("£3,690.22")).toBeNull();
  });

  it("net: guest total is the engine total plus a reconciling taxes & fees line", () => {
    renderWithProviders(<QuoteResultCard quote={grossQuote} basis="net" />);
    // Under NET the engine total is the guest-facing figure.
    expect(screen.getByText("£3,690.22")).toBeInTheDocument();
    // …and the gap over the lines surfaces as taxes & fees (3690.22 − 3195).
    expect(screen.getByText("Taxes & fees")).toBeInTheDocument();
    expect(screen.getByText("£495.22")).toBeInTheDocument();
  });

  it("net: no taxes & fees line when the engine total already equals the line sum", () => {
    const reconciled: PriceQuote = { ...grossQuote, total: "3195" };
    renderWithProviders(<QuoteResultCard quote={reconciled} basis="net" />);
    expect(screen.getByText("£3,195.00")).toBeInTheDocument();
    expect(screen.queryByText("Taxes & fees")).toBeNull();
  });

  it("net: falls back to the line sum when the engine omits total (no £0.00 headline)", () => {
    const noTotal: PriceQuote = { ...grossQuote };
    delete (noTotal as { total?: string }).total;
    renderWithProviders(<QuoteResultCard quote={noTotal} basis="net" />);
    // Must reconcile to the lines, never headline £0.00.
    expect(screen.getByText("£3,195.00")).toBeInTheDocument();
    expect(screen.queryByText("£0.00")).toBeNull();
    expect(screen.queryByText("Taxes & fees")).toBeNull();
  });

  it("net: falls back to the line sum when total is below the lines (breakdown still ties out)", () => {
    // An anomalous total under the line sum would otherwise show lines that
    // exceed the headline; fall back to the reconciled line sum instead.
    const belowLines: PriceQuote = { ...grossQuote, total: "3000" };
    renderWithProviders(<QuoteResultCard quote={belowLines} basis="net" />);
    expect(screen.getByText("£3,195.00")).toBeInTheDocument();
    expect(screen.queryByText("£3,000.00")).toBeNull();
    expect(screen.queryByText("Taxes & fees")).toBeNull();
  });

  it("never renders owner economics; the pending note stands in", () => {
    renderWithProviders(<QuoteResultCard quote={grossQuote} basis="gross" />);
    expect(screen.getByText(/Owner net, commission and tax are pending/)).toBeInTheDocument();
  });
});
