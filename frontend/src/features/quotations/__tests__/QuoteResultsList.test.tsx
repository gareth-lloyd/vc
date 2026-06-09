import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "@/test/render";
import { QuoteResultsList } from "../components/QuoteResultsList";
import type { QuoteOption } from "../schemas";

function option(overrides: Partial<QuoteOption> = {}): QuoteOption {
  return {
    property_id: 1,
    property_name: "Villa Sol",
    hero_image_url: null,
    available: true,
    total: "4500.00",
    ...overrides,
  };
}

const noop = () => undefined;

function renderList(options: QuoteOption[]) {
  return renderWithProviders(
    <QuoteResultsList
      options={options}
      isLoading={false}
      currency="USD"
      stagedPropertyIds={new Set()}
      onAdd={noop}
    />,
  );
}

describe("QuoteResultsList", () => {
  it("renders an available option with its total", () => {
    renderList([option()]);
    expect(screen.getByText("Villa Sol")).toBeInTheDocument();
    expect(screen.getByText("$4,500.00")).toBeInTheDocument();
  });

  it("collapses unavailable options behind a toggle, revealing them on expand", async () => {
    renderList([
      option(),
      option({ property_id: 2, property_name: "Villa Azul", available: false, total: null }),
    ]);

    // The available villa is always visible.
    expect(screen.getByText("Villa Sol")).toBeInTheDocument();

    // The unavailable villa is hidden behind a collapsed toggle so it doesn't
    // eat screen real estate.
    expect(screen.queryByText("Villa Azul")).not.toBeInTheDocument();
    const toggle = screen.getByRole("button", { name: /1 villa unavailable/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    // Expanding the section reveals the unavailable villa.
    await userEvent.click(toggle);
    expect(screen.getByText("Villa Azul")).toBeInTheDocument();
    expect(toggle).toHaveAttribute("aria-expanded", "true");
  });

  it("shows no unavailable toggle when every option is available", () => {
    renderList([option()]);
    expect(screen.queryByRole("button", { name: /unavailable/i })).not.toBeInTheDocument();
  });
});
