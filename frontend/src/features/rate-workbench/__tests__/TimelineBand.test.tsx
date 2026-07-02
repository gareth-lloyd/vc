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
    planId: 5,
    planName: "Summer",
    minPrice: 900,
    maxPrice: 900,
    currencyCode: "EUR",
    priceTier: "high",
    addAfter: { date_from: "2026-09-01" },
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

describe("TimelineBand — add-after affordance", () => {
  it("shows a + that hands the writer the day after the period's end", async () => {
    const user = userEvent.setup();
    const onCreatePeriod = vi.fn();
    renderWithProviders(
      <TimelineBand
        band={rateBand}
        windowStart={windowStart}
        dayCount={dayCount}
        onCreatePeriod={onCreatePeriod}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Add a rate period starting 1 Sep 2026" }));
    expect(onCreatePeriod).toHaveBeenCalledWith({ planId: 5, date_from: "2026-09-01" });
  });

  it("hands the writer a gap-bounded prefill when the next period caps it", async () => {
    const user = userEvent.setup();
    const onCreatePeriod = vi.fn();
    const bounded: WorkbenchBand = {
      ...rateBand,
      meta: { ...rateBand.meta, addAfter: { date_from: "2026-09-01", date_to: "2026-09-14" } },
    };
    renderWithProviders(
      <TimelineBand
        band={bounded}
        windowStart={windowStart}
        dayCount={dayCount}
        onCreatePeriod={onCreatePeriod}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Add a rate period starting 1 Sep 2026" }));
    expect(onCreatePeriod).toHaveBeenCalledWith({
      planId: 5,
      date_from: "2026-09-01",
      date_to: "2026-09-14",
    });
  });

  it("offers no + when the next period is contiguous (no addAfter prefill)", () => {
    const contiguous: WorkbenchBand = {
      ...rateBand,
      meta: { ...rateBand.meta, addAfter: undefined },
    };
    renderWithProviders(
      <TimelineBand
        band={contiguous}
        windowStart={windowStart}
        dayCount={dayCount}
        onCreatePeriod={() => {}}
      />,
    );
    expect(screen.queryByRole("button", { name: /rate period starting/ })).toBeNull();
  });

  it("offers no + without a handler (read-only)", () => {
    renderWithProviders(
      <TimelineBand band={rateBand} windowStart={windowStart} dayCount={dayCount} />,
    );
    expect(screen.queryByRole("button", { name: /rate period starting/ })).toBeNull();
  });

  it("marks a band running past the window with an end-continuation cue instead of a +", () => {
    const crossYear: WorkbenchBand = {
      ...rateBand,
      dateFrom: "2026-11-01",
      dateTo: "2027-02-25",
      dateToExclusive: "2027-02-26",
      // toLanes suppresses the prefill for window-clipped periods.
      meta: { ...rateBand.meta, addAfter: undefined },
    };
    renderWithProviders(
      <TimelineBand
        band={crossYear}
        windowStart={windowStart}
        dayCount={dayCount}
        onCreatePeriod={() => {}}
      />,
    );
    expect(screen.queryByRole("button", { name: /rate period starting/ })).toBeNull();
    expect(screen.getByTestId("band-continues-end")).toBeInTheDocument();
    expect(screen.queryByTestId("band-continues-start")).toBeNull();
  });

  it("marks a band starting before the window with a start-continuation cue", () => {
    const fromLastYear: WorkbenchBand = {
      ...rateBand,
      dateFrom: "2025-12-01",
      dateTo: "2026-01-31",
      dateToExclusive: "2026-02-01",
    };
    renderWithProviders(
      <TimelineBand band={fromLastYear} windowStart={windowStart} dayCount={dayCount} />,
    );
    expect(screen.getByTestId("band-continues-start")).toBeInTheDocument();
    expect(screen.queryByTestId("band-continues-end")).toBeNull();
  });

  it("shows no continuation cues on a band fully inside the window", () => {
    renderWithProviders(
      <TimelineBand band={rateBand} windowStart={windowStart} dayCount={dayCount} />,
    );
    expect(screen.queryByTestId("band-continues-start")).toBeNull();
    expect(screen.queryByTestId("band-continues-end")).toBeNull();
  });

  it("offers no + on non-rates bands even for writers", () => {
    renderWithProviders(
      <TimelineBand
        band={gapBand}
        windowStart={windowStart}
        dayCount={dayCount}
        onCreatePeriod={() => {}}
      />,
    );
    expect(screen.queryByRole("button", { name: /rate period starting/ })).toBeNull();
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
    const onCreatePeriod = vi.fn();
    renderWithProviders(
      <TimelineBand
        band={gapBand}
        windowStart={windowStart}
        dayCount={dayCount}
        onCreatePeriod={onCreatePeriod}
      />,
    );
    // The accessible name must promise the action, not just the information —
    // the hover card is pointer-only.
    await user.click(
      screen.getByRole("button", { name: /No rates, 1 Sep 2026 to 30 Sep 2026 — add/ }),
    );
    expect(onCreatePeriod).toHaveBeenCalledWith({
      planId: 5,
      date_from: "2026-09-01",
      date_to: "2026-09-30",
    });
  });

  it("shows the add-a-period hint on hover for writers", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <TimelineBand
        band={gapBand}
        windowStart={windowStart}
        dayCount={dayCount}
        onCreatePeriod={() => {}}
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
