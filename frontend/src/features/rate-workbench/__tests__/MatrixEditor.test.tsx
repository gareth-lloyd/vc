import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import type { RatePlanDetail } from "@/features/properties/schemas";
import { MatrixEditor } from "../components/MatrixEditor";

// GAP-056: rows are the plan's periods (each owns a date range), columns the
// union of party bands. Period 500 prices 2–4; period 501 prices 5–6 — so each
// row leaves the other band's column empty (and fillable).
const ratePlanDetail: RatePlanDetail = {
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
      ratePlanId={100}
      seasons={[ratePlanDetail]}
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
        return HttpResponse.json({ ...ratePlanDetail.periods[0].bands[0], nightly: "700" });
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
        return HttpResponse.json(ratePlanDetail.periods[0].bands[0]);
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
      ...ratePlanDetail,
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
      <MatrixEditor
        ratePlanId={100}
        seasons={[overlapping]}
        canWrite
        commission={null}
        tax={null}
      />,
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

describe("MatrixEditor — zero-period season (period create CTA)", () => {
  const emptySeason: RatePlanDetail = { ...ratePlanDetail, periods: [] };

  it("shows an Add period CTA for a writer", async () => {
    const onAddPeriod = vi.fn();
    renderWithProviders(
      <MatrixEditor
        ratePlanId={100}
        seasons={[emptySeason]}
        canWrite
        commission={null}
        tax={null}
        onAddPeriod={onAddPeriod}
      />,
    );
    expect(screen.getByText("This season has no rate periods yet.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Add period" }));
    expect(onAddPeriod).toHaveBeenCalledTimes(1);
  });

  it("disables (never hides) the CTA without the write role", () => {
    renderWithProviders(
      <MatrixEditor
        ratePlanId={100}
        seasons={[emptySeason]}
        canWrite={false}
        commission={null}
        tax={null}
        onAddPeriod={() => {}}
      />,
    );
    expect(screen.getByText("This season has no rate periods yet.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add period" })).toBeDisabled();
  });
});

describe("MatrixEditor — first-class band creation (Unit 4)", () => {
  it("opens the band dialog from a period row button, prefilled above the covered range", async () => {
    const user = userEvent.setup();
    const posted: Array<Record<string, unknown>> = [];
    server.use(
      http.post("/api/v1/periods/500/bands", async ({ request }) => {
        posted.push((await request.json()) as Record<string, unknown>);
        return HttpResponse.json(
          { id: 9, period: 500, min_party: 5, max_party: 5, nightly: "800" },
          { status: 201 },
        );
      }),
    );
    renderEditor();

    // Period 500 covers parties 2–4 → the new band starts at 5.
    await user.click(await screen.findByRole("button", { name: /Add band — Early summer/i }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText(/Minimum party/i)).toHaveValue(5);
    expect(within(dialog).getByLabelText(/Maximum party/i)).toHaveValue(5);
    await user.type(within(dialog).getByLabelText(/Nightly price/i), "800");
    await user.click(within(dialog).getByRole("button", { name: /^Save$/i }));

    await waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0]).toMatchObject({ min_party: 5, max_party: 5, nightly: "800" });
  });

  it("turns coverage-gap warnings into clickable chips prefilled with the gap range", async () => {
    const user = userEvent.setup();
    const gappy: RatePlanDetail = {
      ...ratePlanDetail,
      periods: [
        {
          ...ratePlanDetail.periods[0],
          coverage_gaps: [[5, 6]],
        },
        ratePlanDetail.periods[1],
      ],
    };
    renderWithProviders(
      <MatrixEditor ratePlanId={100} seasons={[gappy]} canWrite commission={null} tax={null} />,
    );

    await user.click(await screen.findByRole("button", { name: /Add a band for parties 5–6/i }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText(/Minimum party/i)).toHaveValue(5);
    expect(within(dialog).getByLabelText(/Maximum party/i)).toHaveValue(6);
  });

  it("offers a first-band CTA when the plan's periods have no bands at all", async () => {
    const user = userEvent.setup();
    const bandless: RatePlanDetail = {
      ...ratePlanDetail,
      periods: ratePlanDetail.periods.map((p) => ({ ...p, bands: [], coverage_gaps: [] })),
    };
    renderWithProviders(
      <MatrixEditor ratePlanId={100} seasons={[bandless]} canWrite commission={null} tax={null} />,
    );
    expect(await screen.findByText("This rate period has no bands yet.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Add band" }));
    const dialog = await screen.findByRole("dialog");
    // No coverage yet → seeded at party 1, on the first period.
    expect(within(dialog).getByLabelText(/Minimum party/i)).toHaveValue(1);
  });

  it("offers viewers the gap information as text, without band-create affordances", async () => {
    const gappy: RatePlanDetail = {
      ...ratePlanDetail,
      periods: [{ ...ratePlanDetail.periods[0], coverage_gaps: [[5, 6]] }],
    };
    renderWithProviders(
      <MatrixEditor
        ratePlanId={100}
        seasons={[gappy]}
        canWrite={false}
        commission={null}
        tax={null}
      />,
    );
    expect(await screen.findByText(/unpriced party sizes/i)).toBeInTheDocument();
    expect(screen.getByText(/5–6/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Add a band/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /Add band/i })).toBeNull();
  });
});
