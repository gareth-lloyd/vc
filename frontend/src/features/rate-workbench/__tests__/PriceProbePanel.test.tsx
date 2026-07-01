import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import type { Extra } from "@/features/properties/schemas";
import { PriceProbePanel } from "../components/PriceProbePanel";

const optInExtra: Extra = {
  id: 11,
  property: 7,
  name: "Airport transfer",
  is_mandatory: false,
  is_active: true,
};
const mandatoryExtra: Extra = {
  id: 12,
  property: 7,
  name: "Cleaning fee",
  is_mandatory: true,
  is_active: true,
};

const breakdown = {
  property_id: 7,
  currency_code: "EUR",
  party: 5,
  date_from: "2026-07-12",
  date_to: "2026-07-19",
  lines: [
    { date: "2026-07-12", band_id: 1, period_id: 500, nightly: "900", notes: null },
    { date: "2026-07-13", rule_id: 1, period_id: 500, nightly: "900", notes: null },
  ],
  rate_subtotal: "1800",
  extras: [
    { extra_id: 11, name: "Airport transfer", kind: "flat", calc: "flat", computed_amount: "120" },
  ],
  extras_total: "120",
  discount: "0",
  commission: "700",
  tax: "0",
  total: "1920",
  net_to_owner: "1220",
  plan_id: 100,
  winning_period_id: 500,
  is_projected: false,
  inclusion: "Daily maid\nWelcome hamper",
  occupancy_pricing: true,
};

function renderPanel() {
  return renderWithProviders(
    <PriceProbePanel
      propertyId={7}
      extras={[optInExtra, mandatoryExtra]}
      periodLabels={{ 500: "Summer 2026 · Peak" }}
    />,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("PriceProbePanel", () => {
  it("only offers non-mandatory extras as opt-in toggles", () => {
    renderPanel();
    expect(screen.getByLabelText("Airport transfer")).toBeInTheDocument();
    expect(screen.queryByLabelText("Cleaning fee")).toBeNull();
  });

  it("posts the exact quote body and renders the guest total plus owner economics", async () => {
    let posted: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/pricing:quote", async ({ request }) => {
        posted = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(breakdown);
      }),
    );
    const user = userEvent.setup();
    renderPanel();

    await user.type(screen.getByLabelText("Check-in"), "2026-07-12");
    await user.type(screen.getByLabelText("Check-out"), "2026-07-19");
    const adults = screen.getByLabelText("Adults");
    await user.clear(adults);
    await user.type(adults, "4");
    const children = screen.getByLabelText("Children");
    await user.clear(children);
    await user.type(children, "1");
    await user.click(screen.getByLabelText("Airport transfer"));
    await user.click(screen.getByRole("button", { name: "Get quote" }));

    await waitFor(() => expect(posted).not.toBeNull());
    expect(posted).toEqual({
      property_id: 7,
      date_from: "2026-07-12",
      date_to: "2026-07-19",
      adults: 4,
      children: 1,
      opt_in_extras: [11],
      discount_code: "",
    });

    // Guest total shown; the winning period is named from periodLabels.
    expect(await screen.findByText("Summer 2026 · Peak")).toBeInTheDocument();
    expect(screen.getByText("Guest total")).toBeInTheDocument();
    // Owner economics render from the engine's carve-out figures (BUG-009 fixed).
    expect(screen.getByText("Owner economics")).toBeInTheDocument();
    expect(screen.getByText("€1,220.00")).toBeInTheDocument();
    expect(screen.getByText("€700.00")).toBeInTheDocument();
    // Inclusions surfaced from the newline-joined string.
    expect(screen.getByText("Welcome hamper")).toBeInTheDocument();
  });

  it("shows a friendly message on a 409 no_rate_available", async () => {
    server.use(
      http.post("/api/v1/pricing:quote", () =>
        HttpResponse.json(
          { code: "no_rate_available", detail: "No approved rate for these dates." },
          { status: 409 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderPanel();

    await user.type(screen.getByLabelText("Check-in"), "2026-07-12");
    await user.type(screen.getByLabelText("Check-out"), "2026-07-19");
    await user.click(screen.getByRole("button", { name: "Get quote" }));

    expect(
      await screen.findByText("No rate is available for those dates and party size."),
    ).toBeInTheDocument();
  });

  it("tolerates unknown fields in the response (lenient parse)", async () => {
    server.use(
      http.post("/api/v1/pricing:quote", () =>
        HttpResponse.json({ ...breakdown, some_future_field: 42, another: { nested: true } }),
      ),
    );
    const user = userEvent.setup();
    renderPanel();

    await user.type(screen.getByLabelText("Check-in"), "2026-07-12");
    await user.type(screen.getByLabelText("Check-out"), "2026-07-19");
    await user.click(screen.getByRole("button", { name: "Get quote" }));

    expect(await screen.findByText("Guest total")).toBeInTheDocument();
  });

  it("clears a shown quote when an input changes (no stale result)", async () => {
    server.use(http.post("/api/v1/pricing:quote", () => HttpResponse.json(breakdown)));
    const user = userEvent.setup();
    renderPanel();

    await user.type(screen.getByLabelText("Check-in"), "2026-07-12");
    await user.type(screen.getByLabelText("Check-out"), "2026-07-19");
    await user.click(screen.getByRole("button", { name: "Get quote" }));
    expect(await screen.findByText("Guest total")).toBeInTheDocument();

    // Editing the party count invalidates the shown quote.
    const adults = screen.getByLabelText("Adults");
    await user.clear(adults);
    await user.type(adults, "6");
    expect(screen.queryByText("Guest total")).toBeNull();
  });

  it("keeps Get quote disabled until both dates are chosen", async () => {
    const user = userEvent.setup();
    renderPanel();
    expect(screen.getByRole("button", { name: "Get quote" })).toBeDisabled();
    await user.type(screen.getByLabelText("Check-in"), "2026-07-12");
    expect(screen.getByRole("button", { name: "Get quote" })).toBeDisabled();
    await user.type(screen.getByLabelText("Check-out"), "2026-07-19");
    expect(screen.getByRole("button", { name: "Get quote" })).toBeEnabled();
  });

  // A NET-plan response: the grossed-up `total` (1920 net + 150 commission +
  // 30 tax = 2100) exceeds the line sum, and the gap is a real guest charge.
  const netShaped = {
    ...breakdown,
    total: "2100",
    commission: "150",
    tax: "30",
    net_to_owner: "1920",
    price_basis: "net",
  };

  async function submit(user: ReturnType<typeof userEvent.setup>) {
    await user.type(screen.getByLabelText("Check-in"), "2026-07-12");
    await user.type(screen.getByLabelText("Check-out"), "2026-07-19");
    await user.click(screen.getByRole("button", { name: "Get quote" }));
  }

  it("trusts the engine total for a NET plan and surfaces taxes & fees", async () => {
    server.use(http.post("/api/v1/pricing:quote", () => HttpResponse.json(netShaped)));
    const user = userEvent.setup();
    renderPanel();
    await submit(user);
    // The grossed-up engine total is the guest figure — never recomputed
    // from the lines (the pre-fix workaround would have shown 1,920.00).
    expect(await screen.findByText("€2,100.00")).toBeInTheDocument();
    expect(screen.getByText("Taxes & fees")).toBeInTheDocument();
    expect(screen.getByText("€180.00")).toBeInTheDocument();
  });
});
