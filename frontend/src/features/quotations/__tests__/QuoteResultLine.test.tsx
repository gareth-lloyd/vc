import { afterEach, describe, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "@/test/render";
import { server } from "@/test/msw/server";
import { QuoteResultLine } from "../components/QuoteResultLine";
import type { OccupancyBand, QuoteOption, StayOption } from "../schemas";

afterEach(() => server.resetHandlers());

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

// Two Saturday blocks: the default (priced up front) and an alternative the
// picker reprices on pick.
function twoBlocks(overrides: [Partial<StayOption>?, Partial<StayOption>?] = []): StayOption[] {
  return [
    {
      date_from: "2026-07-04",
      date_to: "2026-07-11",
      nights: 7,
      is_default: true,
      is_available: true,
      ...overrides[0],
    },
    {
      date_from: "2026-07-11",
      date_to: "2026-07-18",
      nights: 7,
      is_default: false,
      is_available: true,
      ...overrides[1],
    },
  ];
}

function band(overrides: Partial<OccupancyBand> = {}): OccupancyBand {
  return {
    min_party: 1,
    max_party: 4,
    adults: 4,
    total: "3000.00",
    currency_code: "USD",
    is_projected: false,
    is_poa: false,
    error_code: null,
    ...overrides,
  };
}

function mockReprice(quote: Record<string, unknown>) {
  const bodies: unknown[] = [];
  server.use(
    http.post("/api/v1/quotations:search-options", async ({ request }) => {
      bodies.push(await request.json());
      return HttpResponse.json({ quotes: [{ property_id: 1, ...quote }] });
    }),
  );
  return bodies;
}

function renderLine(opt: QuoteOption, props: { staged?: boolean; onAdd?: () => void } = {}) {
  return renderWithProviders(
    <QuoteResultLine
      option={opt}
      staged={props.staged ?? false}
      adults={2}
      children={0}
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
    // Legacy-shaped option without stay_options — no chosen stay rides along.
    expect(onAdd).toHaveBeenCalledWith(opt, undefined);

    rerender(<QuoteResultLine option={opt} staged adults={2} children={0} onAdd={onAdd} />);
    expect(screen.getByRole("button", { name: /added/i })).toBeDisabled();
  });

  describe("stay-option picker", () => {
    it("renders no picker for a single stay option and hands it to onAdd as the default", async () => {
      const onAdd = vi.fn();
      renderLine(
        option({
          stay_options: [
            {
              date_from: "2026-07-04",
              date_to: "2026-07-11",
              nights: 7,
              is_default: true,
              is_available: true,
            },
          ],
        }),
        { onAdd },
      );

      expect(screen.queryByRole("radiogroup")).not.toBeInTheDocument();
      await userEvent.click(screen.getByRole("button", { name: /add to quote/i }));
      expect(onAdd).toHaveBeenCalledWith(
        expect.objectContaining({ property_id: 1 }),
        expect.objectContaining({ date_from: "2026-07-04", is_default: true }),
      );
    });

    it("preselects the default block and shows its up-front price", () => {
      renderLine(option({ stay_options: twoBlocks() }));

      const chips = screen.getAllByRole("radio");
      expect(chips).toHaveLength(2);
      expect(chips[0]).toHaveAttribute("aria-checked", "true");
      expect(screen.getByText(/4,500\.00/)).toBeInTheDocument();
    });

    it("reprices a picked alternative block and shows its total", async () => {
      const bodies = mockReprice({
        available: true,
        total: "5200.00",
        currency_code: "USD",
        date_from: "2026-07-11",
        date_to: "2026-07-18",
      });
      renderLine(option({ stay_options: twoBlocks() }));

      await userEvent.click(screen.getAllByRole("radio")[1]);

      await waitFor(() => expect(screen.getByText(/5,200\.00/)).toBeInTheDocument());
      expect(bodies[0]).toEqual({
        flex_days: 0,
        requests: [
          {
            property_id: 1,
            date_from: "2026-07-11",
            date_to: "2026-07-18",
            adults: 2,
            children: 0,
          },
        ],
      });
    });

    it("hands the chosen block's stay to onAdd after a reprice", async () => {
      mockReprice({
        available: true,
        total: "5200.00",
        currency_code: "USD",
        date_from: "2026-07-11",
        date_to: "2026-07-18",
        inclusion: "Pool heating",
      });
      const onAdd = vi.fn();
      renderLine(option({ stay_options: twoBlocks() }), { onAdd });

      await userEvent.click(screen.getAllByRole("radio")[1]);
      await waitFor(() => expect(screen.getByText(/5,200\.00/)).toBeInTheDocument());
      await userEvent.click(screen.getByRole("button", { name: /add to quote/i }));

      expect(onAdd).toHaveBeenCalledWith(
        expect.objectContaining({ property_id: 1 }),
        expect.objectContaining({
          date_from: "2026-07-11",
          date_to: "2026-07-18",
          is_default: false,
          total: "5200.00",
          currency: "USD",
          inclusion: "Pool heating",
        }),
      );
    });

    it("disables Add with an inline error when the reprice fails", async () => {
      server.use(
        http.post("/api/v1/quotations:search-options", () =>
          HttpResponse.json({ detail: "boom" }, { status: 500 }),
        ),
      );
      renderLine(option({ stay_options: twoBlocks() }));

      await userEvent.click(screen.getAllByRole("radio")[1]);

      expect(await screen.findByRole("alert")).toHaveTextContent(/couldn't price/i);
      expect(screen.getByRole("button", { name: /add to quote/i })).toBeDisabled();
    });

    it("surfaces a domain error entry from the reprice inline", async () => {
      mockReprice({
        available: false,
        error_code: "min_nights_not_met",
        error_detail: "RateCard 3 requires min_nights=14, got 7",
      });
      renderLine(option({ stay_options: twoBlocks() }));

      await userEvent.click(screen.getAllByRole("radio")[1]);

      expect(await screen.findByRole("alert")).toHaveTextContent(/min_nights=14/);
      expect(screen.getByRole("button", { name: /add to quote/i })).toBeDisabled();
    });

    it("keeps a held block selectable but disables Add", async () => {
      renderLine(option({ stay_options: twoBlocks([undefined, { is_available: false }]) }));

      await userEvent.click(screen.getAllByRole("radio")[1]);

      // Held chip is selected, but the block can't be added.
      expect(screen.getAllByRole("radio")[1]).toHaveAttribute("aria-checked", "true");
      expect(screen.getByRole("button", { name: /add to quote/i })).toBeDisabled();
    });

    it("preselects the first free block when the default is held, repricing it", async () => {
      mockReprice({
        available: true,
        total: "5200.00",
        currency_code: "USD",
        date_from: "2026-07-11",
        date_to: "2026-07-18",
      });
      renderLine(option({ stay_options: twoBlocks([{ is_available: false }, undefined]) }));

      expect(screen.getAllByRole("radio")[1]).toHaveAttribute("aria-checked", "true");
      await waitFor(() => expect(screen.getByText(/5,200\.00/)).toBeInTheDocument());
      expect(screen.getByRole("button", { name: /add to quote/i })).toBeEnabled();
    });

    it("omits the stay-option picker for a banded result", () => {
      // Plan H3/#9: bands are priced for the default block only, so the
      // alternate-block picker is suppressed even when blocks exist.
      renderLine(
        option({
          occupancy_bands: [band(), band({ min_party: 5, max_party: 8 })],
          stay_options: twoBlocks(),
        }),
      );

      expect(screen.queryByRole("radiogroup")).not.toBeInTheDocument();
      expect(screen.queryByRole("radio")).not.toBeInTheDocument();
    });

    it("flags a reprice whose engine dates differ from the clicked chip", async () => {
      mockReprice({
        available: true,
        total: "5200.00",
        currency_code: "USD",
        date_from: "2026-07-12",
        date_to: "2026-07-19",
        changeover_shifted_from: "2026-07-11",
      });
      renderLine(option({ stay_options: twoBlocks() }));

      await userEvent.click(screen.getAllByRole("radio")[1]);

      expect(await screen.findByText(/Priced as 12 Jul 2026 → 19 Jul 2026/)).toBeInTheDocument();
    });
  });

  describe("occupancy fan-out", () => {
    it("renders each occupancy band as a default-checked, priced row", () => {
      renderLine(
        option({
          total: null,
          occupancy_bands: [
            band({ min_party: 1, max_party: 4, total: "3000.00" }),
            band({ min_party: 5, max_party: 8, total: "4500.00" }),
            band({ min_party: 9, max_party: 12, total: "6000.00" }),
          ],
        }),
      );

      const boxes = screen.getAllByRole("checkbox");
      expect(boxes).toHaveLength(3);
      boxes.forEach((b) => expect(b).toHaveAttribute("aria-checked", "true"));

      expect(screen.getByText(/1–4 guests/)).toBeInTheDocument();
      expect(screen.getByText(/5–8 guests/)).toBeInTheDocument();
      expect(screen.getByText(/9–12 guests/)).toBeInTheDocument();
      expect(screen.getByText("$3,000.00")).toBeInTheDocument();
      expect(screen.getByText("$4,500.00")).toBeInTheDocument();
      expect(screen.getByText("$6,000.00")).toBeInTheDocument();
    });

    it("shows the on-application label for a POA band without crashing", () => {
      renderLine(
        option({
          total: null,
          occupancy_bands: [
            band({ min_party: 1, max_party: 4, total: "3000.00" }),
            band({ min_party: 5, max_party: 8, total: null, currency_code: null, is_poa: true }),
          ],
        }),
      );

      expect(screen.getByText(/on application/i)).toBeInTheDocument();
    });

    it("disables Add when every band is unchecked", async () => {
      renderLine(
        option({
          occupancy_bands: [
            band({ min_party: 1, max_party: 4 }),
            band({ min_party: 5, max_party: 8 }),
          ],
        }),
      );

      expect(screen.getByRole("button", { name: /add to quote/i })).toBeEnabled();
      const boxes = screen.getAllByRole("checkbox");
      await userEvent.click(boxes[0]);
      await userEvent.click(boxes[1]);
      boxes.forEach((b) => expect(b).toHaveAttribute("aria-checked", "false"));
      expect(screen.getByRole("button", { name: /add to quote/i })).toBeDisabled();
    });

    it("keeps Add enabled for a banded result whose default block is booked", () => {
      // A banded result is priced by its bands (default block only), so the
      // stay-block held/reprice machinery must not gate Add: a booked default
      // block (with a free alternate) neither disables Add nor fires a reprice —
      // no reprice mock is registered, so a stray reprice would surface.
      renderLine(
        option({
          occupancy_bands: [
            band({ min_party: 1, max_party: 4 }),
            band({ min_party: 5, max_party: 8 }),
          ],
          stay_options: twoBlocks([{ is_available: false }, undefined]),
        }),
      );

      expect(screen.getByRole("button", { name: /add to quote/i })).toBeEnabled();
      // No block picker and no "held" hint — the banded card ignores blocks.
      expect(screen.queryByRole("radio")).not.toBeInTheDocument();
    });

    it("passes only the checked bands to onAdd", async () => {
      const onAdd = vi.fn();
      renderLine(
        option({
          occupancy_bands: [
            band({ min_party: 1, max_party: 4 }),
            band({ min_party: 5, max_party: 8 }),
          ],
        }),
        { onAdd },
      );

      // Uncheck the first band, then add.
      await userEvent.click(screen.getAllByRole("checkbox")[0]);
      await userEvent.click(screen.getByRole("button", { name: /add to quote/i }));

      const call = onAdd.mock.calls[0];
      expect(call[2]).toHaveLength(1);
      expect(call[2][0]).toMatchObject({ min_party: 5, max_party: 8 });
    });
  });
});
