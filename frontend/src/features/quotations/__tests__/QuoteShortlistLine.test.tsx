import { useState } from "react";
import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "@/test/render";
import { QuoteShortlistLine } from "../components/QuoteShortlistLine";
import { type StagedBand, type StagedLine, stagedLineId } from "../schemas";

function band(overrides: Partial<StagedBand> = {}): StagedBand {
  return {
    min_party: 1,
    max_party: 4,
    adults: 4,
    total: "4500.00",
    currency: "USD",
    is_poa: false,
    checked: true,
    ...overrides,
  };
}

function bandedLine(overrides: Partial<StagedLine> = {}): StagedLine {
  const base = {
    property_id: 7,
    property_name: "Villa Sol",
    hero_image_url: null,
    date_from: "2026-07-01",
    date_to: "2026-07-08",
    priced_date_from: "2026-07-01",
    priced_date_to: "2026-07-08",
    adults: 4,
    children: 0,
    currency: "USD",
    total: null,
    discount: "0",
    inclusions: "",
    price_override_reason: "",
    is_manual: false,
    manual_only: false,
    notes: "",
    occupancy_bands: [
      band({ min_party: 1, max_party: 4, adults: 4, total: "4500.00" }),
      band({ min_party: 5, max_party: 8, adults: 8, total: "6200.00" }),
      band({ min_party: 9, max_party: 12, adults: 12, total: null, is_poa: true }),
    ],
    ...overrides,
  };
  return { line_id: stagedLineId(base.property_id, base.date_from), ...base };
}

// The page owns the staged line; the shortlist edits via onUpdate. Mirror that so
// a band toggle actually re-renders.
function Harness({ initial, expanded = false }: { initial: StagedLine; expanded?: boolean }) {
  const [line, setLine] = useState(initial);
  const [open, setOpen] = useState(expanded);
  return (
    <QuoteShortlistLine
      line={line}
      expanded={open}
      onToggle={() => setOpen((v) => !v)}
      onUpdate={(patch) => setLine((prev) => ({ ...prev, ...patch }))}
      onRemove={() => undefined}
    />
  );
}

describe("QuoteShortlistLine — banded (GAP-044)", () => {
  it("renders each band's price and flags the POA band, with no single total", () => {
    renderWithProviders(<Harness initial={bandedLine()} />);
    expect(screen.getByText("$4,500.00")).toBeInTheDocument();
    expect(screen.getByText("$6,200.00")).toBeInTheDocument();
    // The POA band shows flagged, not priced.
    expect(screen.getByText(/on application/i)).toBeInTheDocument();
    // No summed / headline total for the villa.
    expect(screen.queryByText("$10,700.00")).not.toBeInTheDocument();
  });

  it("toggles a band's checked state via its checkbox", async () => {
    renderWithProviders(<Harness initial={bandedLine()} />);
    const firstBand = screen.getByRole("checkbox", { name: /include the 1–4 guests band/i });
    expect(firstBand).toBeChecked();
    await userEvent.click(firstBand);
    expect(firstBand).not.toBeChecked();
  });

  it("shows the none-checked error once every non-POA band is unchecked", async () => {
    renderWithProviders(<Harness initial={bandedLine()} />);
    await userEvent.click(screen.getByRole("checkbox", { name: /include the 1–4 guests band/i }));
    await userEvent.click(screen.getByRole("checkbox", { name: /include the 5–8 guests band/i }));
    expect(screen.getByText(/select at least one band/i)).toBeInTheDocument();
  });

  it("disables the manual-override toggle for a banded line", async () => {
    renderWithProviders(<Harness initial={bandedLine()} expanded />);
    expect(screen.getByRole("checkbox", { name: /override the price manually/i })).toBeDisabled();
    // A banded line offers no discount field — each band is priced per bracket.
    expect(screen.queryByLabelText(/^discount$/i)).not.toBeInTheDocument();
  });
});
