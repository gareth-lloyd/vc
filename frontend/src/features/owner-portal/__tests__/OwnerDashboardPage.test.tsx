import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { Route, Routes } from "react-router-dom";
import { screen } from "@testing-library/react";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { OwnerDashboardPage } from "../OwnerDashboardPage";

function renderPage() {
  return renderWithProviders(
    <Routes>
      <Route path="/owner/dashboard" element={<OwnerDashboardPage />} />
    </Routes>,
    { route: "/owner/dashboard" },
  );
}

describe("OwnerDashboardPage", () => {
  it("renders KPI values and an upcoming arrival", async () => {
    server.use(
      http.get("/api/v1/owner/dashboard", () =>
        HttpResponse.json({
          ytd: { bookings: 12, gross_revenue: "50000.00", net_to_owner: "40000.00" },
          properties: { total: 3, by_status: { active: 2, draft: 1 } },
          upcoming_arrivals: [
            {
              reference: "VC-0007",
              property_id: 3,
              property_name: "Villa Anemoi",
              date_from: "2026-07-01",
              date_to: "2026-07-08",
              guest_name: "Ada Lovelace",
              adults: 2,
              children: 0,
            },
          ],
        }),
      ),
    );
    renderPage();
    expect(await screen.findByText("12")).toBeInTheDocument();
    expect(screen.getByText("€50,000.00")).toBeInTheDocument();
    expect(screen.getByText("€40,000.00")).toBeInTheDocument();
    expect(screen.getByText("VC-0007")).toBeInTheDocument();
    expect(screen.getByText("Villa Anemoi")).toBeInTheDocument();
  });

  it("shows 'Not shared' when money totals are null", async () => {
    server.use(
      http.get("/api/v1/owner/dashboard", () =>
        HttpResponse.json({
          ytd: { bookings: 4, gross_revenue: null, net_to_owner: null },
          properties: { total: 1, by_status: {} },
          upcoming_arrivals: [],
        }),
      ),
    );
    renderPage();
    expect(await screen.findByText("4")).toBeInTheDocument();
    expect(screen.getAllByText("Not shared").length).toBeGreaterThanOrEqual(2);
  });
});
