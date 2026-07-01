import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import type { RatePlanDetail } from "@/features/properties/schemas";
import { MatrixEditor } from "../components/MatrixEditor";

// GAP-056: rows are the plan's periods (each owns a date range), columns the
// union of party bands. Period 500 prices 2–4; period 501 prices 5–6 — so each
// row leaves the other band's column empty (and fillable).
const seasonDetail: RatePlanDetail = {
  id: 100,
  property: 7,
  name: "Summer 2026",
  currency_code: "EUR",
  price_basis: "gross",
  effective_from: "2026-06-01",
  effective_to: "2026-08-31",
  is_active: true,
  periods: [
    {
      id: 500,
      plan: 100,
      name: "Early summer",
      date_from: "2026-06-01",
      date_to: "2026-06-28",
      is_active: true,
      coverage_gaps: [],
      bands: [{ id: 1, period: 500, min_party: 2, max_party: 4, nightly: "650" }],
    },
    {
      id: 501,
      plan: 100,
      name: "Peak",
      date_from: "2026-06-29",
      date_to: "2026-08-31",
      is_active: true,
      coverage_gaps: [],
      bands: [{ id: 2, period: 501, min_party: 5, max_party: 6, nightly: "900" }],
    },
  ],
};

function renderEditor(canWrite = true) {
  return renderWithProviders(
    <MatrixEditor
      seasonId={100}
      seasons={[seasonDetail]}
      canWrite={canWrite}
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
      http.patch("/api/v1/bands/:id", async ({ params, request }) => {
        const body = await request.json();
        patched.push({ id: String(params.id), body });
        return HttpResponse.json({ ...seasonDetail.periods[0].bands[0], nightly: "700" });
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
      http.patch("/api/v1/bands/:id", () => {
        calls += 1;
        return HttpResponse.json(seasonDetail.periods[0].bands[0]);
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
    // Each period leaves the other band's column empty → fillable (+) buttons.
    const fillButtons = await screen.findAllByRole("button", {
      name: /Add a price for this band/i,
    });
    expect(fillButtons.length).toBeGreaterThan(0);
    await user.click(fillButtons[0]);
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  it("offers no fill button on a cell already covered by another band in its period", async () => {
    // Two periods contribute overlapping columns (2–4 and 3–6): every empty
    // intersection overlaps an existing band in that row's period on the party
    // axis, so filling any would 4xx — the grid must not invite it.
    const overlapping: RatePlanDetail = {
      ...seasonDetail,
      periods: [
        {
          id: 500,
          plan: 100,
          name: "Early summer",
          date_from: "2026-06-01",
          date_to: "2026-06-28",
          is_active: true,
          coverage_gaps: [],
          bands: [{ id: 1, period: 500, min_party: 2, max_party: 4, nightly: "650" }],
        },
        {
          id: 501,
          plan: 100,
          name: "Peak",
          date_from: "2026-06-29",
          date_to: "2026-08-31",
          is_active: true,
          coverage_gaps: [],
          bands: [{ id: 2, period: 501, min_party: 3, max_party: 6, nightly: "1200" }],
        },
      ],
    };
    renderWithProviders(
      <MatrixEditor seasonId={100} seasons={[overlapping]} canWrite commission={null} tax={null} />,
    );
    // Priced cell present; no "+" anywhere (every empty cell is covered).
    expect(await screen.findByLabelText(/Nightly rate, 2026-06-01 to 2026-06-28/i)).toBeEnabled();
    expect(screen.queryByRole("button", { name: /Add a price for this band/i })).toBeNull();
  });

  it("renders read-only cells (disabled inputs, no fill buttons) without write access", async () => {
    renderEditor(false);
    const input = await screen.findByLabelText(/Nightly rate, 2026-06-01 to 2026-06-28/i);
    expect(input).toBeDisabled();
    expect(screen.queryByRole("button", { name: /Add a price for this band/i })).toBeNull();
  });
});
