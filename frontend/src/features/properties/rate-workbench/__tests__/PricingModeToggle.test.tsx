import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import type { RatePlanDetail } from "@/features/properties/schemas";
import { PricingModeToggle } from "../components/PricingModeToggle";

const flatPlan: RatePlanDetail = {
  id: 100,
  property: 7,
  name: "Summer 2026",
  currency_code: "EUR",
  price_basis: "gross",
  prices_by_occupancy: false,
  effective_from: "2026-06-01",
  effective_to: "2026-08-31",
  is_active: true,
  periods: [
    {
      id: 500,
      plan: 100,
      name: "All year",
      date_from: "2026-06-01",
      date_to: "2026-08-31",
      is_active: true,
      coverage_gaps: [],
      bands: [{ id: 1, period: 500, min_party: 1, max_party: 8, nightly: "650" }],
    },
  ],
};

function render(plan: RatePlanDetail, canWrite = true) {
  return renderWithProviders(
    <PricingModeToggle propertyId={7} ratePlan={plan} canWrite={canWrite} />,
  );
}

describe("PricingModeToggle", () => {
  it("switches a flat plan to occupancy via PATCH", async () => {
    const user = userEvent.setup();
    const patched: unknown[] = [];
    server.use(
      http.patch("/api/v1/rate-plans/:id", async ({ request }) => {
        patched.push(await request.json());
        return HttpResponse.json({ ...flatPlan, prices_by_occupancy: true });
      }),
    );
    render(flatPlan);
    await user.click(screen.getByRole("button", { name: "By occupancy" }));
    await waitFor(() => expect(patched).toHaveLength(1));
    expect(patched[0]).toMatchObject({ prices_by_occupancy: true });
  });

  it("reflects the active mode with aria-pressed", () => {
    render(flatPlan);
    expect(screen.getByRole("button", { name: "Flat" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "By occupancy" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("disables the Flat option while an occupancy period has multiple bands", () => {
    const multiBand: RatePlanDetail = {
      ...flatPlan,
      prices_by_occupancy: true,
      periods: [
        {
          ...flatPlan.periods[0],
          bands: [
            { id: 1, period: 500, min_party: 1, max_party: 4, nightly: "650" },
            { id: 2, period: 500, min_party: 5, max_party: 8, nightly: "900" },
          ],
        },
      ],
    };
    render(multiBand);
    expect(screen.getByRole("button", { name: "Flat" })).toBeDisabled();
  });

  it("allows switching to Flat when each period has a single band", async () => {
    const singleBandOccupancy: RatePlanDetail = { ...flatPlan, prices_by_occupancy: true };
    const patched: unknown[] = [];
    server.use(
      http.patch("/api/v1/rate-plans/:id", async ({ request }) => {
        patched.push(await request.json());
        return HttpResponse.json({ ...flatPlan, prices_by_occupancy: false });
      }),
    );
    const user = userEvent.setup();
    render(singleBandOccupancy);
    const flat = screen.getByRole("button", { name: "Flat" });
    expect(flat).toBeEnabled();
    await user.click(flat);
    await waitFor(() => expect(patched).toHaveLength(1));
    expect(patched[0]).toMatchObject({ prices_by_occupancy: false });
  });

  it("disables both options without write access", () => {
    render(flatPlan, false);
    expect(screen.getByRole("button", { name: "Flat" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "By occupancy" })).toBeDisabled();
  });
});
