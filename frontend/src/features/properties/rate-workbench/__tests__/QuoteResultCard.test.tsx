import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/render";
import type { PriceQuote } from "../schemas";
import { QuoteResultCard } from "../components/QuoteResultCard";

// A GROSS-plan quote from the basis-aware engine (BUG-009 fixed): `total`
// equals the line sum (commission+tax are carved OUT of the rate) and the
// owner economics ride along for the owner-side section.
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
  total: "3195.00",
  commission: "430.50",
  tax: "319.50",
  net_to_owner: "2445.00",
  price_basis: "gross",
  plan_id: 35,
  winning_period_id: null,
  is_projected: false,
  occupancy_pricing: false,
};

// A NET-plan quote: `total` is the grossed-up guest figure; the gap over the
// line sum is the commission+tax the guest pays on top of the owner net.
const netQuote: PriceQuote = {
  ...grossQuote,
  total: "3690.22",
  commission: "300.00",
  tax: "195.22",
  net_to_owner: "3195.00",
  price_basis: "net",
};

describe("QuoteResultCard", () => {
  it("gross: headlines the engine total (equal to the line sum), no taxes & fees line", () => {
    renderWithProviders(<QuoteResultCard quote={grossQuote} />);
    expect(screen.getByText("Guest total")).toBeInTheDocument();
    expect(screen.getByText("£3,195.00")).toBeInTheDocument();
    // Commission+tax are inside the gross rate — no additive guest line.
    expect(screen.queryByText("Taxes & fees")).toBeNull();
  });

  it("gross: renders the owner economics section from the engine figures", () => {
    renderWithProviders(<QuoteResultCard quote={grossQuote} />);
    expect(screen.getByText("Owner economics")).toBeInTheDocument();
    expect(screen.getByText("Net to owner")).toBeInTheDocument();
    expect(screen.getByText("£2,445.00")).toBeInTheDocument();
    expect(screen.getByText("Commission")).toBeInTheDocument();
    expect(screen.getByText("£430.50")).toBeInTheDocument();
    expect(screen.getByText("Tax")).toBeInTheDocument();
    expect(screen.getByText("£319.50")).toBeInTheDocument();
    // The old BUG-009 pending note is gone.
    expect(screen.queryByText(/pending the finance rewrite/)).toBeNull();
  });

  it("net: headlines the engine total and reconciles the gap as taxes & fees", () => {
    renderWithProviders(<QuoteResultCard quote={netQuote} />);
    expect(screen.getByText("£3,690.22")).toBeInTheDocument();
    // The gap over the lines (300.00 + 195.22) is a real guest-facing charge.
    expect(screen.getByText("Taxes & fees")).toBeInTheDocument();
    expect(screen.getByText("£495.22")).toBeInTheDocument();
    // The same money, owner-side: the net the owner keeps.
    expect(screen.getByText("Net to owner")).toBeInTheDocument();
    expect(screen.getByText("£3,195.00")).toBeInTheDocument();
  });

  it("falls back to the line sum when the engine omits total (no £0.00 headline)", () => {
    const noTotal: PriceQuote = { ...grossQuote };
    delete (noTotal as { total?: string }).total;
    renderWithProviders(<QuoteResultCard quote={noTotal} />);
    expect(screen.getByText("£3,195.00")).toBeInTheDocument();
    expect(screen.queryByText("£0.00")).toBeNull();
    expect(screen.queryByText("Taxes & fees")).toBeNull();
  });

  it("legacy shape without price_basis: the total-over-lines gap is the taxes & fees fallback", () => {
    const legacy: PriceQuote = { ...netQuote };
    delete (legacy as { price_basis?: string }).price_basis;
    delete (legacy as { commission?: string }).commission;
    delete (legacy as { tax?: string }).tax;
    delete (legacy as { net_to_owner?: string }).net_to_owner;
    renderWithProviders(<QuoteResultCard quote={legacy} />);
    expect(screen.getByText("£3,690.22")).toBeInTheDocument();
    expect(screen.getByText("Taxes & fees")).toBeInTheDocument();
    expect(screen.getByText("£495.22")).toBeInTheDocument();
  });

  it("marks a non-commissionable applied extra, leaving commissionable ones unmarked (GAP-076)", () => {
    const withExtras: PriceQuote = {
      ...grossQuote,
      extras: [
        { extra_id: 1, name: "Cleaning", computed_amount: "100", commissionable: false },
        { extra_id: 2, name: "Linen", computed_amount: "50", commissionable: true },
      ],
    };
    renderWithProviders(<QuoteResultCard quote={withExtras} />);
    expect(screen.getByText("Cleaning")).toBeInTheDocument();
    expect(screen.getByText("Linen")).toBeInTheDocument();
    expect(screen.getAllByText("Non-commissionable")).toHaveLength(1);
  });

  it("hides owner economics when the response carries no owner fields (legacy shape)", () => {
    const legacy: PriceQuote = { ...grossQuote };
    delete (legacy as { commission?: string }).commission;
    delete (legacy as { tax?: string }).tax;
    delete (legacy as { net_to_owner?: string }).net_to_owner;
    renderWithProviders(<QuoteResultCard quote={legacy} />);
    expect(screen.getByText("£3,195.00")).toBeInTheDocument();
    expect(screen.queryByText("Owner economics")).toBeNull();
  });
});
