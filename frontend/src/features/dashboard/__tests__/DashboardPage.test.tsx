import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { server } from "@/test/msw/server";
import { drfPage } from "@/test/drf";
import { renderWithProviders } from "@/test/render";
import { DashboardPage } from "../DashboardPage";

const booking = {
  id: 101,
  reference: "BK-0001",
  status: "deposit_paid" as const,
  property: 1,
  guest: 1,
  date_from: "2026-05-25",
  date_to: "2026-06-01",
  adults: 2,
  children: 0,
  currency: 1,
  rental_price: "1000.00",
  balance_due: "500.00",
  site_source: "main_website",
  property_name: "Villa Azul",
  guest_name: "Mooney Family",
};

const enquiry = {
  id: 7,
  reference: "EN-AAA-007",
  status: "new" as const,
  guest: null,
  first_name: "Ada",
  last_name: "Lovelace",
  email: "ada@example.com",
  property: null,
  region: null,
  date_from: "2026-08-01",
  date_to: "2026-08-08",
  adults: 4,
  children: 2,
  request_type: "quote" as const,
  assigned_to: null,
  agent: null,
  site_source: "main_website" as const,
  created_at: "2026-05-20T10:00:00Z",
  updated_at: "2026-05-20T10:00:00Z",
};

function bookingsHandler(results: unknown[], opts: { count?: number } = {}) {
  return http.get("/api/v1/bookings", () =>
    HttpResponse.json({ ...drfPage(results), count: opts.count ?? results.length }),
  );
}

function enquiriesHandler(results: unknown[], opts: { count?: number } = {}) {
  return http.get("/api/v1/enquiries", () =>
    HttpResponse.json({ ...drfPage(results), count: opts.count ?? results.length }),
  );
}

describe("DashboardPage", () => {
  it("renders KPI counts plus arrivals and recent enquiries", async () => {
    server.use(bookingsHandler([booking], { count: 4 }), enquiriesHandler([enquiry], { count: 9 }));

    renderWithProviders(<DashboardPage />);

    await waitFor(() => {
      // KPI for check-ins today should show booking count
      expect(screen.getByText("Check-ins today")).toBeInTheDocument();
    });

    // All four KPI cards render with their backend counts
    const fours = await screen.findAllByText("4");
    expect(fours.length).toBeGreaterThan(0);

    expect(screen.getByText("Check-outs today")).toBeInTheDocument();
    expect(screen.getByText("New enquiries")).toBeInTheDocument();
    expect(screen.getByText("Awaiting balance")).toBeInTheDocument();

    // Arrivals row + recent-enquiries row both rendered
    expect(await screen.findByText("Villa Azul")).toBeInTheDocument();
    expect(await screen.findByText("Ada Lovelace")).toBeInTheDocument();
  });

  it("shows empty state when there is nothing to do today", async () => {
    server.use(bookingsHandler([], { count: 0 }), enquiriesHandler([], { count: 0 }));

    renderWithProviders(<DashboardPage />);

    expect(await screen.findByText("Nothing arriving today. Enjoy the quiet.")).toBeInTheDocument();
    expect(await screen.findByText("No enquiries yet.")).toBeInTheDocument();
  });

  it("isolates errors per widget", async () => {
    server.use(
      http.get("/api/v1/bookings", () => HttpResponse.json({ detail: "boom" }, { status: 500 })),
      enquiriesHandler([enquiry], { count: 1 }),
    );

    renderWithProviders(<DashboardPage />);

    // Enquiries side still loads
    expect(await screen.findByText("Ada Lovelace")).toBeInTheDocument();
    // Bookings side shows an error in at least one place (the arrivals section)
    const errors = await screen.findAllByText("Couldn't load this card.");
    expect(errors.length).toBeGreaterThan(0);
  });
});
