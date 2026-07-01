import { http, HttpResponse } from "msw";
import { Navigate, Route, Routes } from "react-router-dom";
import { describe, expect, it, afterEach } from "vitest";
import { screen } from "@testing-library/react";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { drfPage } from "@/test/drf";
import { useAuthStore } from "@/features/auth/store";
import { PropertyDetailLayout } from "@/features/properties/PropertyDetailLayout";
import { RateWorkbenchPage } from "../RateWorkbenchPage";

const propertyFixture = {
  id: 7,
  name: "Casa Sur",
  display_name: "Casa Sur",
  slug: "casa-sur",
  licence_number: "ETV-7777",
  status: "active",
  channel: "direct",
  category: null,
  group: null,
  region: null,
  feature_ids: [],
  legacy_id: null,
  created_at: "2025-01-01T00:00:00Z",
  updated_at: "2026-05-01T00:00:00Z",
};

const season = {
  id: 100,
  property: 7,
  name: "Summer 2026",
  currency_code: "EUR",
  effective_from: "2026-06-01",
  effective_to: "2026-08-31",
  is_active: true,
};

const ratePlanDetail = {
  ...season,
  periods: [
    {
      id: 500,
      plan: 100,
      name: "Standard",
      date_from: "2026-06-01",
      date_to: "2026-06-28",
      is_active: true,
      coverage_gaps: [],
      bands: [{ id: 1, period: 500, min_party: 1, max_party: 8, nightly: "650" }],
    },
    {
      id: 501,
      plan: 100,
      name: "Peak",
      date_from: "2026-06-29",
      date_to: "2026-08-31",
      is_active: true,
      coverage_gaps: [],
      bands: [{ id: 2, period: 501, min_party: 1, max_party: 8, nightly: "900" }],
    },
  ],
};

const service = {
  id: 9,
  property: 7,
  name: "Daily maid",
  copy: "Included",
  sort_order: 0,
  is_active: true,
};
const extra = {
  id: 11,
  property: 7,
  name: "Airport transfer",
  amount: "120",
  currency_code: "EUR",
};
const discount = { id: 21, property: 7, name: "Early bird", code: "EARLY", amount: "10" };
const changeover = {
  id: 31,
  property: 7,
  weekday: "sat",
  effective_from: "2026-06-01",
  effective_to: "2026-08-31",
};

function installHandlers() {
  server.use(
    http.get("/api/v1/properties/casa-sur", () => HttpResponse.json(propertyFixture)),
    http.get("/api/v1/properties/7/rate-plans", () => HttpResponse.json(drfPage([season]))),
    http.get("/api/v1/rate-plans/100", () => HttpResponse.json(ratePlanDetail)),
    http.get("/api/v1/properties/7/services", () => HttpResponse.json(drfPage([service]))),
    http.get("/api/v1/properties/7/extras", () => HttpResponse.json(drfPage([extra]))),
    http.get("/api/v1/properties/7/discounts", () => HttpResponse.json(drfPage([discount]))),
    http.get("/api/v1/properties/7/change-over-rules", () =>
      HttpResponse.json(drfPage([changeover])),
    ),
  );
}

function setUser(role: string, is_staff = true) {
  useAuthStore.getState().setMe(
    {
      id: 1,
      email: "a@test.com",
      first_name: "A",
      last_name: "T",
      is_active: true,
      is_staff,
      is_superuser: false,
      preferred_language: "en",
      role,
    },
    { role, is_superuser: false, permissions: [] },
  );
}

function setup(route: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/properties/:id" element={<PropertyDetailLayout />}>
        <Route index element={<Navigate to="details" replace />} />
        <Route path="details" element={<div>details tab</div>} />
        <Route path="rate-workbench" element={<RateWorkbenchPage />} />
      </Route>
    </Routes>,
    { route },
  );
}

afterEach(() => useAuthStore.getState().clear());

describe("RateWorkbenchPage", () => {
  it("renders all six lanes with bands for the reservations role", async () => {
    setUser("reservations");
    installHandlers();
    setup("/properties/casa-sur/rate-workbench");

    expect(
      await screen.findByRole("heading", { name: /Rate & Service Workbench/i }),
    ).toBeInTheDocument();
    // Bands render (once data loads) as buttons with descriptive aria labels
    // (no in-band text). Awaiting one confirms the timeline mounted.
    expect(await screen.findByRole("button", { name: /Summer 2026/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Standard/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Airport transfer/ })).toBeInTheDocument();
    // Lane labels
    expect(screen.getByText("Seasons")).toBeInTheDocument();
    expect(screen.getByText("Rate periods")).toBeInTheDocument();
    expect(screen.getByText("Changeover")).toBeInTheDocument();
  });

  it("shows the tab in nav for a writer but hides it for a read-only user", async () => {
    setUser("reservations");
    installHandlers();
    setup("/properties/casa-sur/rate-workbench");
    expect(await screen.findByRole("link", { name: "Rate Workbench" })).toBeInTheDocument();
    useAuthStore.getState().clear();

    setUser("readonly", false);
    setup("/properties/casa-sur/details");
    expect(await screen.findByText("details tab")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Rate Workbench" })).not.toBeInTheDocument();
  });

  it("shows the empty state when the property has no configuration", async () => {
    setUser("reservations");
    server.use(
      http.get("/api/v1/properties/casa-sur", () => HttpResponse.json(propertyFixture)),
      http.get("/api/v1/properties/7/rate-plans", () => HttpResponse.json(drfPage([]))),
      http.get("/api/v1/properties/7/services", () => HttpResponse.json(drfPage([]))),
      http.get("/api/v1/properties/7/extras", () => HttpResponse.json(drfPage([]))),
      http.get("/api/v1/properties/7/discounts", () => HttpResponse.json(drfPage([]))),
      http.get("/api/v1/properties/7/change-over-rules", () => HttpResponse.json(drfPage([]))),
    );
    setup("/properties/casa-sur/rate-workbench");
    expect(await screen.findByText(/No configuration yet/i)).toBeInTheDocument();
  });

  it("distinguishes config in another year from no config at all", async () => {
    setUser("reservations");
    // A season configured only for 2025; the page defaults to the current year
    // (2026) so no bands are visible — but the property IS configured.
    const pastSeason = { ...season, effective_from: "2025-06-01", effective_to: "2025-08-31" };
    server.use(
      http.get("/api/v1/properties/casa-sur", () => HttpResponse.json(propertyFixture)),
      http.get("/api/v1/properties/7/rate-plans", () => HttpResponse.json(drfPage([pastSeason]))),
      http.get("/api/v1/rate-plans/100", () => HttpResponse.json({ ...pastSeason, periods: [] })),
      http.get("/api/v1/properties/7/services", () => HttpResponse.json(drfPage([]))),
      http.get("/api/v1/properties/7/extras", () => HttpResponse.json(drfPage([]))),
      http.get("/api/v1/properties/7/discounts", () => HttpResponse.json(drfPage([]))),
      http.get("/api/v1/properties/7/change-over-rules", () => HttpResponse.json(drfPage([]))),
    );
    setup("/properties/casa-sur/rate-workbench");
    expect(await screen.findByText(/Nothing scheduled in 2026/i)).toBeInTheDocument();
    expect(screen.queryByText(/No configuration yet/i)).not.toBeInTheDocument();
  });
});
