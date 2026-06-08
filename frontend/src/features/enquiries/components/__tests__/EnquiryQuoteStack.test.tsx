import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/render";
import type { QuotationDetail } from "@/features/quotations/schemas";
import { EnquiryQuoteStack } from "../EnquiryQuoteStack";

function makeQuote(
  partial: Partial<QuotationDetail> & { id: number; reference: string },
): QuotationDetail {
  return {
    status: "draft",
    currency: "GBP",
    lines: [],
    ...partial,
  } as QuotationDetail;
}

describe("EnquiryQuoteStack", () => {
  it("shows an empty state when there are no quotes", () => {
    renderWithProviders(<EnquiryQuoteStack quotations={[]} />);
    expect(screen.getByText(/no quotes/i)).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("renders one deep-linked card per quote with the raw status", () => {
    renderWithProviders(
      <EnquiryQuoteStack
        quotations={[
          makeQuote({ id: 10, reference: "QVC10", status: "sent" }),
          makeQuote({ id: 11, reference: "QVC11", status: "draft" }),
        ]}
      />,
    );

    const first = screen.getByRole("link", { name: /QVC10/ });
    expect(first).toHaveAttribute("href", "/quotations/10");
    expect(screen.getByRole("link", { name: /QVC11/ })).toHaveAttribute("href", "/quotations/11");
    // Raw enum surfaced (capitalisation is CSS) — matches the quotes list.
    expect(screen.getByText("sent")).toBeInTheDocument();
    expect(screen.getByText("draft")).toBeInTheDocument();
  });

  it("summarises the option count and price range across lines", () => {
    renderWithProviders(
      <EnquiryQuoteStack
        quotations={[
          makeQuote({
            id: 12,
            reference: "QVC12",
            currency: "GBP",
            lines: [
              { id: 1, total: "1000.00" },
              { id: 2, total: "1500.00" },
            ] as QuotationDetail["lines"],
          }),
        ]}
      />,
    );

    expect(screen.getByText(/2 options/i)).toBeInTheDocument();
    expect(screen.getByText("£1,000.00 – £1,500.00")).toBeInTheDocument();
  });

  it("shows a single price when a quote has one priced line", () => {
    renderWithProviders(
      <EnquiryQuoteStack
        quotations={[
          makeQuote({
            id: 13,
            reference: "QVC13",
            currency: "GBP",
            lines: [{ id: 3, total: "2400.00" }] as QuotationDetail["lines"],
          }),
        ]}
      />,
    );

    expect(screen.getByText(/1 option\b/i)).toBeInTheDocument();
    expect(screen.getByText("£2,400.00")).toBeInTheDocument();
  });
});
