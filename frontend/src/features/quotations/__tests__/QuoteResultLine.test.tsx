import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "@/test/render";
import { QuoteResultLine } from "../components/QuoteResultLine";
import type { QuoteOption } from "../schemas";

function option(overrides: Partial<QuoteOption> = {}): QuoteOption {
  return {
    property_id: 1,
    property_name: "Villa Sol",
    hero_image_url: null,
    available: true,
    total: "4500.00",
    currency: "USD",
    ...overrides,
  };
}

function renderLine(opt: QuoteOption, props: { staged?: boolean; onAdd?: () => void } = {}) {
  return renderWithProviders(
    <QuoteResultLine
      option={opt}
      staged={props.staged ?? false}
      onAdd={props.onAdd ?? (() => {})}
    />,
  );
}

describe("QuoteResultLine", () => {
  it("renders the changeover day, min nights, and capacity on the meta line", () => {
    renderLine(
      option({ bedrooms: 4, sleeps: 8, changeover_day: "sat", min_nights: 7, max_nights: 14 }),
    );

    expect(
      screen.getByText(/4 bedrooms · sleeps 8 · Sat changeover · min 7 nights/),
    ).toBeInTheDocument();
  });

  it("shows 'no fixed changeover' when the day is explicitly unconstrained", () => {
    renderLine(option({ changeover_day: null, min_nights: 5 }));

    expect(screen.getByText(/no fixed changeover · min 5 nights/)).toBeInTheDocument();
  });

  it("does not claim 'no fixed changeover' for enrichment-less legacy responses", () => {
    renderLine(option({ bedrooms: 4 }));

    expect(screen.queryByText(/no fixed changeover/)).not.toBeInTheDocument();
  });

  it("omits an unconstraining min_nights of 1", () => {
    renderLine(option({ changeover_day: "sat", min_nights: 1 }));

    expect(screen.queryByText(/min 1 night/)).not.toBeInTheDocument();
    expect(screen.getByText(/Sat changeover/)).toBeInTheDocument();
  });

  it("badges occupancy-based pricing and projected rates", () => {
    renderLine(option({ occupancy_pricing: true, is_projected: true }));

    expect(screen.getByText("Occupancy-based pricing")).toBeInTheDocument();
    expect(screen.getByText("Projected rates")).toBeInTheDocument();
  });

  it("shows no badges when neither flag is set", () => {
    renderLine(option({ occupancy_pricing: false, is_projected: false }));

    expect(screen.queryByText("Occupancy-based pricing")).not.toBeInTheDocument();
    expect(screen.queryByText("Projected rates")).not.toBeInTheDocument();
  });

  it("renders short inclusions in full with no toggle", () => {
    renderLine(option({ inclusion: "Daily maid service" }));

    expect(screen.getByText(/Daily maid service/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /show more/i })).not.toBeInTheDocument();
  });

  it("truncates long inclusions behind a Show more toggle", async () => {
    const long = `Daily maid service, ${"pool heating, ".repeat(15)}welcome hamper`;
    renderLine(option({ inclusion: long }));

    expect(screen.queryByText(new RegExp("welcome hamper"))).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /show more/i }));
    expect(screen.getByText(/welcome hamper/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /show less/i }));
    expect(screen.queryByText(/welcome hamper/)).not.toBeInTheDocument();
  });

  it("invokes onAdd and reflects the staged state", async () => {
    const onAdd = vi.fn();
    const opt = option();
    const { rerender } = renderLine(opt, { onAdd });

    await userEvent.click(screen.getByRole("button", { name: /add to quote/i }));
    expect(onAdd).toHaveBeenCalledWith(opt);

    rerender(<QuoteResultLine option={opt} staged onAdd={onAdd} />);
    expect(screen.getByRole("button", { name: /added/i })).toBeDisabled();
  });
});
