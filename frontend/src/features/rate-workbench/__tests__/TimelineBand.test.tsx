import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "@/test/render";
import type { WorkbenchBand } from "../toLanes";
import { TimelineBand } from "../components/TimelineBand";

const windowStart = new Date(Date.UTC(2026, 0, 1));
const dayCount = 365;

const rateBand: WorkbenchBand = {
  id: "card-50",
  laneKey: "rates",
  dateFrom: "2026-06-01",
  dateTo: "2026-08-31",
  label: "Standard",
  sourceId: 50,
  sublane: 0,
  meta: {
    planName: "Summer",
    minPrice: 900,
    maxPrice: 900,
    currencyCode: "EUR",
    priceTier: "high",
  },
};

describe("TimelineBand", () => {
  it("renders a labelled trigger and no detail until interacted with", () => {
    renderWithProviders(
      <TimelineBand band={rateBand} windowStart={windowStart} dayCount={dayCount} />,
    );
    expect(screen.getByRole("button", { name: /Standard/ })).toBeInTheDocument();
    // Detail is not mounted until hover/focus.
    expect(screen.queryByText("Season")).toBeNull();
  });

  it("reveals the band detail on hover", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <TimelineBand band={rateBand} windowStart={windowStart} dayCount={dayCount} />,
    );
    await user.hover(screen.getByRole("button", { name: /Standard/ }));
    // BandDetail surfaces the plan ("Season") row for a rate band.
    expect(await screen.findByText("Season")).toBeInTheDocument();
  });

  it("reveals the band detail on keyboard focus", async () => {
    renderWithProviders(
      <TimelineBand band={rateBand} windowStart={windowStart} dayCount={dayCount} />,
    );
    screen.getByRole("button", { name: /Standard/ }).focus();
    await waitFor(() => expect(screen.getByText("Season")).toBeInTheDocument());
  });
});
