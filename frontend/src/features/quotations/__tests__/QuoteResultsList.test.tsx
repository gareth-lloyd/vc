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
      stagedKeys={new Set<string>()}
      onAdd={noop}
      adults={2}
      children={0}
      searchKey="2026-07-01:2026-07-08:0"
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

  it("disambiguates same-named villas with internal name and capacity", () => {
    // Distinct properties can share a guest-facing display name — the card
    // must carry enough to tell them apart.
    renderList([
      option({ internal_name: "Mary Gardens", bedrooms: 4, sleeps: 8 }),
      option({
        property_id: 2,
        internal_name: "Kelly Corner",
        bedrooms: 6,
        sleeps: 12,
        total: "6100.00",
      }),
    ]);
    expect(screen.getByText(/Mary Gardens/)).toBeInTheDocument();
    expect(screen.getByText(/Kelly Corner/)).toBeInTheDocument();
    expect(screen.getByText(/4 bedrooms · sleeps 8/)).toBeInTheDocument();
    expect(screen.getByText(/6 bedrooms · sleeps 12/)).toBeInTheDocument();
  });

  it("omits the internal name when it matches the display name", () => {
    renderList([option({ internal_name: "Villa Sol", bedrooms: 3, sleeps: 6 })]);
    // The name renders once (as the title), not again in the meta line.
    expect(screen.getAllByText(/Villa Sol/)).toHaveLength(1);
    expect(screen.getByText(/3 bedrooms · sleeps 6/)).toBeInTheDocument();
  });

  it("renders no meta line when the option carries no disambiguators", () => {
    renderList([option()]);
    expect(screen.queryByText(/bedrooms/)).not.toBeInTheDocument();
    expect(screen.queryByText(/sleeps/)).not.toBeInTheDocument();
  });

  it("shows the meta line on unavailable cards too", async () => {
    renderList([
      option({
        property_id: 2,
        property_name: "Villa Azul",
        internal_name: "Thomas Brook",
        bedrooms: 5,
        sleeps: 10,
        available: false,
        total: null,
      }),
    ]);
    await userEvent.click(screen.getByRole("button", { name: /1 villa unavailable/i }));
    expect(screen.getByText(/Thomas Brook/)).toBeInTheDocument();
    expect(screen.getByText(/5 bedrooms · sleeps 10/)).toBeInTheDocument();
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

  it("renders a no-rate option in the main list, flagged, with an Add manually button", () => {
    // Q-013: legacy keeps NO RATE villas selectable — never hide them.
    renderList([
      option(),
      option({
        property_id: 2,
        property_name: "Villa Azul",
        available: false,
        total: null,
        currency: "EUR",
        error_code: "no_rate_available",
        error_detail: "No rate rule covers 2026-09-10 to 2026-09-17.",
      }),
    ]);

    // Visible without expanding anything, flagged where the price would be.
    expect(screen.getByText("Villa Azul")).toBeInTheDocument();
    expect(screen.getByText(/incomplete pricing/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /add manually/i })).toBeEnabled();
    // It is NOT in a collapsed unavailable section.
    expect(screen.queryByRole("button", { name: /unavailable/i })).not.toBeInTheDocument();
  });

  it("exposes the flagged card to assistive tech: labelled article, focusable tooltip trigger", async () => {
    renderList([
      option({
        property_id: 2,
        property_name: "Villa Azul",
        available: false,
        total: null,
        error_code: "no_rate_available",
        error_detail: "RateBand 7 is POA for these dates.",
      }),
    ]);

    // The article carries an aria-label, mirroring the unavailable cards.
    expect(screen.getByLabelText(/villa azul — incomplete pricing/i)).toBeInTheDocument();

    // The badge is keyboard-focusable so the error_detail tooltip (the only
    // place POA is distinguished from a rate-card gap) opens on focus.
    const badge = screen.getByText(/incomplete pricing/i);
    expect(badge).toHaveAttribute("tabindex", "0");
    badge.focus();
    expect(await screen.findAllByText(/rateBand 7 is POA/i)).not.toHaveLength(0);
  });

  it("invokes onAdd with the no-rate option and shows added state once staged", async () => {
    const onAdd = vi.fn();
    const noRate = option({
      property_id: 2,
      property_name: "Villa Azul",
      available: false,
      total: null,
      error_code: "no_rate_available",
    });
    const { rerender } = renderWithProviders(
      <QuoteResultsList
        options={[noRate]}
        isLoading={false}
        stagedKeys={new Set<string>()}
        onAdd={onAdd}
        adults={2}
        children={0}
        searchKey="2026-07-01:2026-07-08:0"
        hasMore={false}
        isLoadingMore={false}
        totalMatched={1}
        onLoadMore={noop}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /add manually/i }));
    expect(onAdd).toHaveBeenCalledWith(noRate);

    rerender(
      <QuoteResultsList
        options={[noRate]}
        isLoading={false}
        stagedKeys={new Set(["2:2026-07-01"])}
        onAdd={onAdd}
        adults={2}
        children={0}
        searchKey="2026-07-01:2026-07-08:0"
        hasMore={false}
        isLoadingMore={false}
        totalMatched={1}
        onLoadMore={noop}
      />,
    );
    expect(screen.getByRole("button", { name: /added/i })).toBeDisabled();
  });

  it("routes a banded but unavailable option (B2) to a full card with its bands", () => {
    // GAP-044 B2: party-out-of-range yet still carries populated bands — it
    // must render the full card (so the bands show), not the compact
    // unavailable row.
    renderList([
      option({
        property_id: 2,
        property_name: "Villa Azul",
        available: false,
        total: null,
        error_code: "party_out_of_range",
        occupancy_bands: [
          {
            min_party: 1,
            max_party: 4,
            adults: 4,
            total: "3000.00",
            currency_code: "USD",
            is_projected: false,
            is_poa: false,
            error_code: null,
          },
          {
            min_party: 5,
            max_party: 8,
            adults: 8,
            total: "4500.00",
            currency_code: "USD",
            is_projected: false,
            is_poa: false,
            error_code: null,
          },
        ],
      }),
    ]);

    // Visible without expanding a collapsed section, with its band rows.
    expect(screen.getByText("Villa Azul")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /unavailable/i })).not.toBeInTheDocument();
    expect(screen.getByText(/1–4 guests/)).toBeInTheDocument();
    expect(screen.getByText(/5–8 guests/)).toBeInTheDocument();
    expect(screen.getAllByRole("checkbox")).toHaveLength(2);
  });

  it("keeps a booked banded week in the compact unavailable list, not a fan-out card", () => {
    // GAP-044 decision 3: bands are gated on the week being date-available. A
    // booked week (dates_unavailable) carries bands from the backend but must
    // not render an addable fan-out — it collapses like any other booked villa.
    renderList([
      option(),
      option({
        property_id: 2,
        property_name: "Villa Azul",
        available: false,
        total: null,
        error_code: "dates_unavailable",
        occupancy_bands: [
          {
            min_party: 1,
            max_party: 4,
            adults: 4,
            total: "3000.00",
            currency_code: "USD",
            is_projected: false,
            is_poa: false,
            error_code: null,
          },
          {
            min_party: 5,
            max_party: 8,
            adults: 8,
            total: "4500.00",
            currency_code: "USD",
            is_projected: false,
            is_poa: false,
            error_code: null,
          },
        ],
      }),
    ]);
    // Collapsed behind the unavailable toggle — no visible band rows / checkboxes.
    expect(screen.queryByText("Villa Azul")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /1 villa unavailable/i })).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("keeps other error codes collapsed and unselectable", () => {
    renderList([
      option(),
      option({
        property_id: 2,
        property_name: "Villa Azul",
        available: false,
        total: null,
        error_code: "party_out_of_range",
      }),
    ]);
    // Hidden behind the collapsed toggle, exactly as before Q-013.
    expect(screen.queryByText("Villa Azul")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /1 villa unavailable/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /add manually/i })).not.toBeInTheDocument();
  });

  it("excludes flagged no-rate cards from the available count", () => {
    renderList(
      [
        option(),
        option({
          property_id: 2,
          property_name: "Villa Azul",
          available: false,
          total: null,
          error_code: "no_rate_available",
        }),
      ],
      { totalMatched: 120 },
    );
    // The flagged card is visible in the list but isn't "available".
    expect(screen.getByText(/1 available · checked 2 of 120 matching villas/i)).toBeInTheDocument();
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
    // 1 available, 2 checked this far, of 120 matching candidates. "Checked"
    // (not "priced") because the count includes unavailable villas the engine
    // never priced.
    expect(screen.getByText(/1 available · checked 2 of 120 matching villas/i)).toBeInTheDocument();
  });

  it("renders Load more only when there are more pages, and calls onLoadMore", async () => {
    const onLoadMore = vi.fn();
    const { rerender } = renderList([option()], { hasMore: false });
    expect(screen.queryByRole("button", { name: /load more/i })).not.toBeInTheDocument();

    rerender(
      <QuoteResultsList
        options={[option()]}
        isLoading={false}
        stagedKeys={new Set<string>()}
        onAdd={noop}
        adults={2}
        children={0}
        searchKey="2026-07-01:2026-07-08:0"
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
