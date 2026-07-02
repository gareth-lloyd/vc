import { describe, expect, it, vi } from "vitest";
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
  dateToExclusive: "2026-09-01",
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

const gapBand: WorkbenchBand = {
  id: "coverage-2026-09-01",
  laneKey: "coverage",
  dateFrom: "2026-09-01",
  dateTo: "2026-09-30",
  dateToExclusive: "2026-10-01",
  label: "Summer",
  sourceId: 5,
  sublane: 0,
  meta: { isGap: true, planId: 5, planName: "Summer" },
};

const noRatesBand: WorkbenchBand = {
  id: "period-50",
  laneKey: "rates",
  dateFrom: "2026-06-01",
  dateTo: "2026-06-30",
  dateToExclusive: "2026-07-01",
  label: "Empty period",
  sourceId: 50,
  sublane: 0,
  meta: { planName: "Summer", minPrice: null, maxPrice: null, hasPoa: false, noRates: true },
};

describe("TimelineBand — coverage gaps", () => {
  it("clicking a gap hands the writer its inclusive date range", async () => {
    const user = userEvent.setup();
    const onGapClick = vi.fn();
    renderWithProviders(
      <TimelineBand
        band={gapBand}
        windowStart={windowStart}
        dayCount={dayCount}
        onGapClick={onGapClick}
      />,
    );
    // The accessible name must promise the action, not just the information —
    // the hover card is pointer-only.
    await user.click(
      screen.getByRole("button", { name: /No rates, 1 Sep 2026 to 30 Sep 2026 — add/ }),
    );
    expect(onGapClick).toHaveBeenCalledWith({ from: "2026-09-01", to: "2026-09-30" });
  });

  it("shows the add-a-period hint on hover for writers", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <TimelineBand
        band={gapBand}
        windowStart={windowStart}
        dayCount={dayCount}
        onGapClick={() => {}}
      />,
    );
    await user.hover(screen.getByRole("button", { name: /No rates/ }));
    expect(await screen.findByText(/Add a rate period/i)).toBeInTheDocument();
  });

  it("keeps the gap visible but inert without a gap-click handler (read-only)", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <TimelineBand band={gapBand} windowStart={windowStart} dayCount={dayCount} />,
    );
    // Plain informational name — no action promised the viewer can't take.
    const band = screen.getByRole("button", { name: "No rates, 1 Sep 2026 to 30 Sep 2026" });
    await user.click(band);
    // Read affordance stays: hovering still explains the gap, minus the action hint.
    await user.hover(band);
    expect(await screen.findByText(/1 Sep 2026/)).toBeInTheDocument();
    expect(screen.queryByText(/Add a rate period/i)).toBeNull();
  });

  it("labels a zero-band period and notes it has no rates yet", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <TimelineBand band={noRatesBand} windowStart={windowStart} dayCount={dayCount} />,
    );
    await user.hover(screen.getByRole("button", { name: /Empty period/ }));
    expect(await screen.findByText(/No rates yet/i)).toBeInTheDocument();
  });
});
