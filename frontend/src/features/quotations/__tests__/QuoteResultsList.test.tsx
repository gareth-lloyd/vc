import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "@/test/render";
import { QuoteResultsList } from "../components/QuoteResultsList";
import type { HiddenCapacityProperty, QuoteOption } from "../schemas";

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

const noop = () => undefined;

interface RenderOpts {
  hiddenForCapacity?: HiddenCapacityProperty[];
  hasMore?: boolean;
  isLoadingMore?: boolean;
  totalMatched?: number;
  onLoadMore?: () => void;
}

function renderList(options: QuoteOption[], opts: RenderOpts = {}) {
  return renderWithProviders(
    <QuoteResultsList
      options={options}
      hiddenForCapacity={opts.hiddenForCapacity ?? []}
      isLoading={false}
      stagedPropertyIds={new Set()}
      onAdd={noop}
      hasMore={opts.hasMore ?? false}
      isLoadingMore={opts.isLoadingMore ?? false}
      totalMatched={opts.totalMatched ?? options.length}
      onLoadMore={opts.onLoadMore ?? noop}
    />,
  );
}

describe("QuoteResultsList", () => {
  it("renders an available option with its total", () => {
    renderList([option()]);
    expect(screen.getByText("Villa Sol")).toBeInTheDocument();
    expect(screen.getByText("$4,500.00")).toBeInTheDocument();
  });

  it("renders mixed-currency results each in their own currency", () => {
    // No builder-level currency (GAP-014) — one list freely mixes £/€/$.
    renderList([
      option({ currency: "GBP" }),
      option({ property_id: 2, property_name: "Villa Azul", total: "5200.00", currency: "EUR" }),
    ]);
    expect(screen.getByText("£4,500.00")).toBeInTheDocument();
    expect(screen.getByText("€5,200.00")).toBeInTheDocument();
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

  it("surfaces a capacity-hidden property as a hint with a link to its details", () => {
    renderList([option()], {
      hiddenForCapacity: [{ id: 307, name: "iCal Demo Villa", slug: "ical-demo" }],
    });
    const link = screen.getByRole("link", { name: "iCal Demo Villa" });
    expect(link).toHaveAttribute("href", "/properties/ical-demo/details");
    expect(screen.getByText(/capacity isn't set/i)).toBeInTheDocument();
  });

  it("shows the capacity hint even when there are no priced options", () => {
    renderList([], { hiddenForCapacity: [{ id: 307, name: "iCal Demo Villa", slug: null }] });
    // Falls back to the id in the link when the property has no slug.
    expect(screen.getByRole("link", { name: "iCal Demo Villa" })).toHaveAttribute(
      "href",
      "/properties/307/details",
    );
  });

  it("renders no hint when nothing is hidden for capacity", () => {
    renderList([option()]);
    expect(screen.queryByText(/capacity isn't set/i)).not.toBeInTheDocument();
  });

  it("shows the priced count so a no-new-available load isn't mysterious", () => {
    renderList(
      [option(), option({ property_id: 2, property_name: "Villa Azul", available: false })],
      { totalMatched: 120 },
    );
    // 1 available, 2 priced this far, of 120 matching candidates.
    expect(screen.getByText(/1 available · priced 2 of 120 matching villas/i)).toBeInTheDocument();
  });

  it("renders Load more only when there are more pages, and calls onLoadMore", async () => {
    const onLoadMore = vi.fn();
    const { rerender } = renderList([option()], { hasMore: false });
    expect(screen.queryByRole("button", { name: /load more/i })).not.toBeInTheDocument();

    rerender(
      <QuoteResultsList
        options={[option()]}
        isLoading={false}
        stagedPropertyIds={new Set()}
        onAdd={noop}
        hasMore
        isLoadingMore={false}
        totalMatched={120}
        onLoadMore={onLoadMore}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /load more/i }));
    expect(onLoadMore).toHaveBeenCalledOnce();
  });

  it("disables Load more while a page is being priced", () => {
    renderList([option()], { hasMore: true, isLoadingMore: true });
    expect(screen.getByRole("button", { name: /loading/i })).toBeDisabled();
  });
});
