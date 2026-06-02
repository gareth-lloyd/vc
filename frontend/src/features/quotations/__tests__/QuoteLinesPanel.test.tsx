import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/render";
import { QuoteLinesPanel } from "../components/QuoteLinesPanel";
import type { StagedLine } from "../schemas";

function stagedLine(overrides: Partial<StagedLine> = {}): StagedLine {
  return {
    property_id: 7,
    property_name: "Villa Sol",
    hero_image_url: null,
    date_from: "2026-07-01",
    date_to: "2026-07-08",
    priced_date_from: "2026-07-01",
    priced_date_to: "2026-07-08",
    adults: 2,
    children: 0,
    total: "4500.00",
    is_manual: false,
    notes: "",
    ...overrides,
  };
}

describe("QuoteLinesPanel", () => {
  it("displays the priced dates and a shift note when the arrival was moved", () => {
    renderWithProviders(
      <QuoteLinesPanel
        lines={[
          stagedLine({
            // Requested 1 Jul, engine priced the changeover-day stay from 4 Jul.
            date_from: "2026-07-01",
            date_to: "2026-07-08",
            priced_date_from: "2026-07-04",
            priced_date_to: "2026-07-11",
          }),
        ]}
        currency="USD"
        onRemove={() => undefined}
      />,
    );
    // The priced (shifted) dates are shown, not the requested ones.
    expect(screen.getByText(/4 Jul 2026 – 11 Jul 2026/)).toBeInTheDocument();
    // The note names the original requested arrival.
    expect(
      screen.getByText(/arrival moved from .+ to the property's changeover day/i),
    ).toBeInTheDocument();
  });

  it("shows no shift note when the priced dates match what was requested", () => {
    renderWithProviders(
      <QuoteLinesPanel lines={[stagedLine()]} currency="USD" onRemove={() => undefined} />,
    );
    expect(screen.getByText(/1 Jul 2026 – 8 Jul 2026/)).toBeInTheDocument();
    expect(
      screen.queryByText(/moved from .+ to the property's changeover day/i),
    ).not.toBeInTheDocument();
  });
});
