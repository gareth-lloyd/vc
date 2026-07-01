import { afterEach, describe, expect, it, vi } from "vitest";
import { http, HttpResponse, delay } from "msw";
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

    it("makes a held block non-selectable, leaving the bookable default active", async () => {
      renderLine(option({ stay_options: twoBlocks([undefined, { is_available: false }]) }));

      const radios = screen.getAllByRole("radio");
      // A booked week can't be quoted, so its chip is disabled — clicking is a no-op.
      expect(radios[1]).toBeDisabled();
      await userEvent.click(radios[1]);

      // The bookable default stays selected and addable.
      expect(radios[0]).toHaveAttribute("aria-checked", "true");
      expect(radios[1]).toHaveAttribute("aria-checked", "false");
      expect(screen.getByRole("button", { name: /add to quote/i })).toBeEnabled();
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

    it("shows the stay-option picker AND the default week's bands (GAP-044b two-axis)", () => {
      // Both axes on one card now: the week chips and the default week's bands.
      renderLine(
        option({
          total: null,
          occupancy_bands: [band(), band({ min_party: 5, max_party: 8, total: "4500.00" })],
          stay_options: twoBlocks(),
        }),
      );

      expect(screen.getAllByRole("radio")).toHaveLength(2);
      expect(screen.getAllByRole("checkbox")).toHaveLength(2);
      expect(screen.getByText("$3,000.00")).toBeInTheDocument();
      expect(screen.getByText("$4,500.00")).toBeInTheDocument();
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

    it("reprices the free alternate on mount when a banded villa's default block is booked", async () => {
      // GAP-044b (H1): with the picker now shown for banded villas, a booked
      // default preselects the first free alternate and reprices it on mount —
      // the same behaviour flat-rate villas already have. Its bands arrive from
      // the reprice, and Add enables once they do.
      mockReprice({
        available: true,
        date_from: "2026-07-11",
        date_to: "2026-07-18",
        occupancy_bands: [
          band({ min_party: 1, max_party: 4, total: "3100.00" }),
          band({ min_party: 5, max_party: 8, total: "4600.00" }),
        ],
      });
      renderLine(
        option({
          total: null,
          occupancy_bands: [
            band({ min_party: 1, max_party: 4 }),
            band({ min_party: 5, max_party: 8 }),
          ],
          stay_options: twoBlocks([{ is_available: false }, undefined]),
        }),
      );

      expect(screen.getAllByRole("radio")[1]).toHaveAttribute("aria-checked", "true");
      await waitFor(() => expect(screen.getByText("$3,100.00")).toBeInTheDocument());
      expect(screen.getByText("$4,600.00")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /add to quote/i })).toBeEnabled();
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

    it("forwards a checked POA band to onAdd (filtered only at save) while Add stays enabled", async () => {
      // The Add gate counts saveable (non-POA, priced) bands, but the payload
      // forwards ALL checked bands — a checked POA band rides along so the
      // shortlist can show it flagged; it's dropped at save (SaveQuoteDialog),
      // not here. This pins that gate-vs-payload seam.
      const onAdd = vi.fn();
      renderLine(
        option({
          total: null,
          occupancy_bands: [
            band({ min_party: 1, max_party: 4, total: "3000.00" }),
            band({ min_party: 5, max_party: 8, total: null, currency_code: null, is_poa: true }),
          ],
        }),
        { onAdd },
      );

      // A priced band stays checked, so Add is enabled despite the POA band.
      expect(screen.getByRole("button", { name: /add to quote/i })).toBeEnabled();
      await userEvent.click(screen.getByRole("button", { name: /add to quote/i }));

      const call = onAdd.mock.calls[0];
      expect(call[2]).toHaveLength(2);
      expect(call[2].map((b: OccupancyBand) => b.is_poa)).toEqual([false, true]);
    });
  });

  describe("two-axis picker (week × bands)", () => {
    // A banded villa with two changeover blocks. The default week's bands are
    // priced up front; picking the alternate reprices to that week's bands.
    function bandedTwoBlocks(overrides: Partial<QuoteOption> = {}): QuoteOption {
      return option({
        total: null,
        occupancy_bands: [
          band({ min_party: 1, max_party: 4, total: "3000.00" }),
          band({ min_party: 5, max_party: 8, total: "4500.00" }),
        ],
        stay_options: twoBlocks(),
        ...overrides,
      });
    }

    it("reprices a picked week and shows that week's bands, preserving a deselection", async () => {
      mockReprice({
        available: true,
        date_from: "2026-07-11",
        date_to: "2026-07-18",
        occupancy_bands: [
          band({ min_party: 1, max_party: 4, total: "3200.00" }),
          band({ min_party: 5, max_party: 8, total: "4700.00" }),
        ],
      });
      renderLine(bandedTwoBlocks());

      // Deselect the 1–4 band on the default week...
      await userEvent.click(screen.getAllByRole("checkbox")[0]);
      expect(screen.getAllByRole("checkbox")[0]).toHaveAttribute("aria-checked", "false");

      // ...flip to the alternate week: its band prices load...
      await userEvent.click(screen.getAllByRole("radio")[1]);
      await waitFor(() => expect(screen.getByText("$3,200.00")).toBeInTheDocument());
      expect(screen.getByText("$4,700.00")).toBeInTheDocument();

      // ...and the 1–4 deselection carried across the flip (by party-range identity).
      expect(screen.getAllByRole("checkbox")[0]).toHaveAttribute("aria-checked", "false");
      expect(screen.getAllByRole("checkbox")[1]).toHaveAttribute("aria-checked", "true");
    });

    it("still renders bands and enables Add for an out-of-bracket week (available:false)", async () => {
      // B2/H2: an out-of-bracket party reprices to available:false yet carries
      // the full band array — the bands stay saveable, Add stays enabled, and
      // no reprice error surfaces.
      mockReprice({
        available: false,
        error_code: "party_out_of_range",
        error_detail: "20 guests exceeds all brackets",
        date_from: "2026-07-11",
        date_to: "2026-07-18",
        occupancy_bands: [
          band({ min_party: 1, max_party: 4, total: "3200.00" }),
          band({ min_party: 5, max_party: 8, total: "4700.00" }),
        ],
      });
      renderLine(bandedTwoBlocks());

      await userEvent.click(screen.getAllByRole("radio")[1]);
      await waitFor(() => expect(screen.getByText("$3,200.00")).toBeInTheDocument());
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: /add to quote/i })).toBeEnabled();
    });

    it("renders a single total when the picked week is flat (no bands)", async () => {
      // A villa banded on the default week can be flat on another (seasonal
      // card boundary): the price area follows the selected week's shape.
      mockReprice({
        available: true,
        total: "5200.00",
        currency_code: "USD",
        date_from: "2026-07-11",
        date_to: "2026-07-18",
      });
      renderLine(bandedTwoBlocks());

      expect(screen.getAllByRole("checkbox")).toHaveLength(2);
      await userEvent.click(screen.getAllByRole("radio")[1]);
      await waitFor(() => expect(screen.getByText(/5,200\.00/)).toBeInTheDocument());
      expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    });

    it("shows a repricing placeholder and disables Add while a picked week loads", async () => {
      server.use(
        http.post("/api/v1/quotations:search-options", async () => {
          await delay("infinite");
          return HttpResponse.json({ quotes: [] });
        }),
      );
      renderLine(bandedTwoBlocks());

      await userEvent.click(screen.getAllByRole("radio")[1]);
      expect(await screen.findByText(/repricing…/i)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /add to quote/i })).toBeDisabled();
    });

    it("flags a changeover shift on a picked banded week", async () => {
      mockReprice({
        available: true,
        date_from: "2026-07-12",
        date_to: "2026-07-19",
        changeover_shifted_from: "2026-07-11",
        occupancy_bands: [
          band({ min_party: 1, max_party: 4, total: "3200.00" }),
          band({ min_party: 5, max_party: 8, total: "4700.00" }),
        ],
      });
      renderLine(bandedTwoBlocks());

      await userEvent.click(screen.getAllByRole("radio")[1]);
      expect(await screen.findByText(/Priced as 12 Jul 2026 → 19 Jul 2026/)).toBeInTheDocument();
    });

    it("makes a held week non-selectable on a banded villa, keeping the default addable", async () => {
      renderLine(
        bandedTwoBlocks({ stay_options: twoBlocks([undefined, { is_available: false }]) }),
      );

      // Default (free) week: Add enabled with bands.
      expect(screen.getByRole("button", { name: /add to quote/i })).toBeEnabled();
      // The held alternate is disabled — clicking it doesn't move the selection.
      const radios = screen.getAllByRole("radio");
      expect(radios[1]).toBeDisabled();
      await userEvent.click(radios[1]);
      expect(radios[0]).toHaveAttribute("aria-checked", "true");
      expect(screen.getByRole("button", { name: /add to quote/i })).toBeEnabled();
    });

    it("hands the picked week's dates and its checked bands to onAdd", async () => {
      mockReprice({
        available: true,
        date_from: "2026-07-11",
        date_to: "2026-07-18",
        occupancy_bands: [
          band({ min_party: 1, max_party: 4, total: "3200.00" }),
          band({ min_party: 5, max_party: 8, total: "4700.00" }),
        ],
      });
      const onAdd = vi.fn();
      renderLine(bandedTwoBlocks(), { onAdd });

      await userEvent.click(screen.getAllByRole("radio")[1]);
      await waitFor(() => expect(screen.getByText("$3,200.00")).toBeInTheDocument());
      // Trim the 1–4 band, then add the alternate week.
      await userEvent.click(screen.getAllByRole("checkbox")[0]);
      await userEvent.click(screen.getByRole("button", { name: /add to quote/i }));

      const call = onAdd.mock.calls[0];
      // Stay carries the picked week's dates (not the default), no single total.
      expect(call[1]).toMatchObject({
        date_from: "2026-07-11",
        date_to: "2026-07-18",
        is_default: false,
        total: null,
        currency: null,
      });
      // Only the still-checked 5–8 band rides along, at the picked week's price.
      expect(call[2]).toHaveLength(1);
      expect(call[2][0]).toMatchObject({ min_party: 5, max_party: 8, total: "4700.00" });
    });
  });
});
