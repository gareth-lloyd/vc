import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import type { RatePlanDetail } from "@/features/properties/schemas";
import { MatrixEditor } from "../components/MatrixEditor";

const seasonDetail: RatePlanDetail = {
  id: 100,
  property: 7,
  name: "Summer 2026",
  currency_code: "EUR",
  price_basis: "gross",
  effective_from: "2026-06-01",
  effective_to: "2026-08-31",
  is_active: true,
  cards: [
    {
      id: 500,
      plan: 100,
      name: "Standard",
      rules: [
        {
          id: 1,
          card: 500,
          date_from: "2026-06-01",
          date_to: "2026-06-28",
          min_party: 2,
          max_party: 4,
          nightly: "650",
        },
        // 2-4 for the Jul segment is left empty → a fillable cell
        {
          id: 2,
          card: 500,
          date_from: "2026-06-29",
          date_to: "2026-08-31",
          min_party: 5,
          max_party: 6,
          nightly: "900",
        },
      ],
    },
  ],
};

function renderEditor(canWrite = true) {
  return renderWithProviders(
    <MatrixEditor
      seasonId={100}
      seasons={[seasonDetail]}
      canWrite={canWrite}
      changeoverDay={null}
      minNightsRental={null}
      commission={null}
      tax={null}
    />,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("MatrixEditor", () => {
  it("PATCHes the rule with a new nightly (clearing POA) when a cell is edited inline", async () => {
    const user = userEvent.setup();
    const patched: Array<{ id: string; body: unknown }> = [];
    server.use(
      http.patch("/api/v1/rules/:id", async ({ params, request }) => {
        const body = await request.json();
        patched.push({ id: String(params.id), body });
        return HttpResponse.json({ ...seasonDetail.cards[0].rules[0], nightly: "700" });
      }),
    );

    renderEditor();
    const input = await screen.findByLabelText(/Nightly rate, 2026-06-01 to 2026-06-28/i);
    await user.clear(input);
    await user.type(input, "700");
    await user.tab(); // blur commits

    await waitFor(() => expect(patched).toHaveLength(1));
    expect(patched[0].id).toBe("1");
    expect(patched[0].body).toMatchObject({ nightly: "700", is_poa: false });
  });

  it("does not PATCH when the value is unchanged", async () => {
    const user = userEvent.setup();
    let calls = 0;
    server.use(
      http.patch("/api/v1/rules/:id", () => {
        calls += 1;
        return HttpResponse.json(seasonDetail.cards[0].rules[0]);
      }),
    );

    renderEditor();
    const input = await screen.findByLabelText(/Nightly rate, 2026-06-01 to 2026-06-28/i);
    await user.click(input);
    await user.tab();

    // Give any (unexpected) request a tick to land.
    await new Promise((r) => setTimeout(r, 20));
    expect(calls).toBe(0);
  });

  it("opens the create dialog seeded from an empty cell", async () => {
    const user = userEvent.setup();
    renderEditor();
    // The Jul segment × 2-4 band has no rule → a fill (+) button.
    const fillButtons = await screen.findAllByRole("button", {
      name: /Add a price for this band/i,
    });
    expect(fillButtons.length).toBeGreaterThan(0);
    await user.click(fillButtons[0]);
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  it("offers no fill button on a cell already covered by another band's rule", async () => {
    // Base band (2–4) across the season + a large-party peak band (5–8) for a
    // sub-range: legal data, but every empty intersection overlaps an existing
    // rule, so filling any would 4xx — the grid must not invite it.
    const overlapping: RatePlanDetail = {
      ...seasonDetail,
      cards: [
        {
          id: 500,
          plan: 100,
          name: "Standard",
          rules: [
            {
              id: 1,
              card: 500,
              date_from: "2026-06-01",
              date_to: "2026-08-31",
              min_party: 2,
              max_party: 4,
              nightly: "650",
            },
            {
              id: 2,
              card: 500,
              date_from: "2026-07-01",
              date_to: "2026-07-31",
              min_party: 5,
              max_party: 8,
              nightly: "1200",
            },
          ],
        },
      ],
    };
    renderWithProviders(
      <MatrixEditor
        seasonId={100}
        seasons={[overlapping]}
        canWrite
        changeoverDay={null}
        minNightsRental={null}
        commission={null}
        tax={null}
      />,
    );
    // Both priced cells present; no "+" anywhere (both empty cells are covered).
    expect(await screen.findByLabelText(/Nightly rate, 2026-06-01 to 2026-08-31/i)).toBeEnabled();
    expect(screen.queryByRole("button", { name: /Add a price for this band/i })).toBeNull();
  });

  it("renders read-only cells (disabled inputs, no fill buttons) without write access", async () => {
    renderEditor(false);
    const input = await screen.findByLabelText(/Nightly rate, 2026-06-01 to 2026-06-28/i);
    expect(input).toBeDisabled();
    expect(screen.queryByRole("button", { name: /Add a price for this band/i })).toBeNull();
  });
});
