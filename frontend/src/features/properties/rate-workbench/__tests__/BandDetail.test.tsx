import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/render";
import type { WorkbenchBand } from "../toLanes";
import { BandDetail } from "../components/BandDetail";

const rateBand = (meta: WorkbenchBand["meta"]): WorkbenchBand => ({
  id: "period-50",
  laneKey: "rates",
  dateFrom: "2026-06-01",
  dateTo: "2026-08-31",
  dateToExclusive: "2026-09-01",
  label: "Summer",
  sourceId: 50,
  sublane: 0,
  meta: {
    planId: 5,
    planName: "Peak",
    currencyCode: "EUR",
    ...meta,
  },
});

describe("BandDetail — reductions (Q-018)", () => {
  it("shows the effective price with a 'reduced from' base plus reason and date", () => {
    renderWithProviders(
      <BandDetail
        band={rateBand({
          minPrice: 160,
          maxPrice: 160,
          hasReduction: true,
          baseMinPrice: 200,
          baseMaxPrice: 200,
          reductionReason: "Late-season push",
          reducedAt: "2026-05-01T09:00:00Z",
        })}
      />,
    );
    // Effective price is the headline price row.
    expect(screen.getByText("€160.00")).toBeInTheDocument();
    // Base price under an explicit "Reduced from" term.
    expect(screen.getByText("Reduced from")).toBeInTheDocument();
    expect(screen.getByText("€200.00")).toBeInTheDocument();
    expect(screen.getByText("Reason")).toBeInTheDocument();
    expect(screen.getByText("Late-season push")).toBeInTheDocument();
    expect(screen.getByText("Reduced on")).toBeInTheDocument();
    expect(screen.getByText("1 May 2026")).toBeInTheDocument();
  });

  it("formats a reduced-from range when the period's bands span prices", () => {
    renderWithProviders(
      <BandDetail
        band={rateBand({
          minPrice: 160,
          maxPrice: 720,
          hasReduction: true,
          baseMinPrice: 200,
          baseMaxPrice: 900,
        })}
      />,
    );
    expect(screen.getByText("Reduced from")).toBeInTheDocument();
    expect(screen.getByText(/€200\.00\s*–\s*€900\.00/)).toBeInTheDocument();
  });

  it("omits the reduction rows entirely for an unreduced band", () => {
    renderWithProviders(<BandDetail band={rateBand({ minPrice: 200, maxPrice: 200 })} />);
    expect(screen.getByText("€200.00")).toBeInTheDocument();
    expect(screen.queryByText("Reduced from")).toBeNull();
    expect(screen.queryByText("Reduced on")).toBeNull();
  });
});
