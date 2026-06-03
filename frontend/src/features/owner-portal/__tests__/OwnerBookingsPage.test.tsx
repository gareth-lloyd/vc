import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { Route, Routes } from "react-router-dom";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { drfPage } from "@/test/drf";
import { OwnerBookingsPage } from "../OwnerBookingsPage";

const baseRow = {
  id: 7,
  reference: "VC-0007",
  status: "deposit_paid",
  property_id: 3,
  property_name: "Villa Anemoi",
  date_from: "2026-07-01",
  date_to: "2026-07-08",
  adults: 2,
  children: 0,
  currency_code: "EUR",
  guest_name: "Ada Lovelace",
  guest_country: { code: "GB", name: "United Kingdom" },
  is_repeat_guest: false,
};

function renderPage() {
  return renderWithProviders(
    <Routes>
      <Route path="/owner/bookings" element={<OwnerBookingsPage />} />
      <Route path="/owner/bookings/:id" element={<div>Detail 7</div>} />
    </Routes>,
    { route: "/owner/bookings" },
  );
}

describe("OwnerBookingsPage", () => {
  it("renders rows and hides the money column when redacted", async () => {
    server.use(http.get("/api/v1/owner/bookings", () => HttpResponse.json(drfPage([baseRow]))));
    renderPage();
    expect(await screen.findByText("VC-0007")).toBeInTheDocument();
    expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.queryByText("Rental price")).not.toBeInTheDocument();
  });

  it("shows the money column and value when rental_price is present", async () => {
    server.use(
      http.get("/api/v1/owner/bookings", () =>
        HttpResponse.json(drfPage([{ ...baseRow, rental_price: "1500.00", balance_due: "0.00" }])),
      ),
    );
    renderPage();
    expect(await screen.findByText("VC-0007")).toBeInTheDocument();
    expect(screen.getByText("Rental price")).toBeInTheDocument();
    expect(screen.getByText("€1,500.00")).toBeInTheDocument();
  });

  it("navigates to the detail on row click", async () => {
    server.use(http.get("/api/v1/owner/bookings", () => HttpResponse.json(drfPage([baseRow]))));
    renderPage();
    await userEvent.click(await screen.findByText("VC-0007"));
    await waitFor(() => expect(screen.getByText("Detail 7")).toBeInTheDocument());
  });
});
